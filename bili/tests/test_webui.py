"""WebUI regression tests: no real services, credentials or upstream requests."""
import http.client
import importlib.util
import json
import os
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location('webui_app', Path(__file__).resolve().parents[1] / 'webui/app.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class IsolatedConfigTest(unittest.TestCase):
    """配置目录隔离：任何用例写 live/replay/auto.env 都落在临时目录，不碰线上配置。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        overrides = {'CONFIG_DIR': root, 'LIVE_ENV': root / 'live.env',
                     'REPLAY_ENV': root / 'replay.env', 'AUTO_ENV': root / 'auto.env'}
        for name, value in overrides.items():
            patcher = mock.patch.object(app, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)


class WebUITest(IsolatedConfigTest):
    def test_first_sync_private_atomic_and_shell_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / 'config'
            session = root / 'session.json'
            code = "test'\"$NOT_EXPANDED`false`&value"
            session.write_text(json.dumps({'rtmp_addr': 'rtmp://example/', 'rtmp_code': code}))
            output = config / 'push.env'
            # 账号档案目录一并隔离：否则 session_file() 会回落到真实的
            # ~/.config/bili/accounts/live.json，让测试读到线上凭证
            with mock.patch.dict(os.environ, {'BILI_ACCOUNTS_DIR': str(root / 'no-accounts')}), \
                    mock.patch.object(app, 'CONFIG_DIR', config), mock.patch.object(app, 'PUSH_ENV', output), mock.patch.object(app, 'SESSION_FILE', session):
                app.sync_push_env()
                app.sync_push_env()
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertEqual(config.stat().st_mode & 0o777, 0o700)
            result = subprocess.run(['bash', '-c', 'source "$1"; printf "%s" "$BILIBILI_PUSH_CODE"', 'test', str(output)], capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, code)
            self.assertEqual(list(config.iterdir()), [output])

    def test_session_file_follows_live_account_profile(self):
        """多账号后 WebUI 必须读 live 账号档案，而不是写死的老路径。"""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            accounts = root / 'accounts'
            accounts.mkdir()
            live = accounts / 'live.json'
            live.write_text(json.dumps({'rtmp_addr': 'rtmp://live/', 'rtmp_code': 'live-code'}))
            (accounts / 'upload.json').write_text(json.dumps({'rtmp_addr': 'rtmp://up/', 'rtmp_code': 'upload-code'}))
            (accounts / 'defaults.json').write_text(json.dumps({'live': 'live', 'upload': 'upload'}))
            with mock.patch.dict(os.environ, {'BILI_ACCOUNTS_DIR': str(accounts)}), \
                    mock.patch.object(app, 'SESSION_FILE', root / 'missing-legacy.json'):
                self.assertEqual(app.session_file(), live)
                # 切走 live 默认账号后 WebUI 应跟随
                (accounts / 'defaults.json').write_text(json.dumps({'live': 'upload'}))
                self.assertEqual(app.session_file(), accounts / 'upload.json')

    def test_concurrent_controls_rejected_and_lock_released(self):
        entered, release = threading.Event(), threading.Event()
        errors = []
        def block(*args):
            entered.set()
            if not release.wait(3):
                raise RuntimeError('test timeout')
        def stop():
            try:
                app.stop_all()
            except Exception as exc:
                errors.append(exc)
        with mock.patch.object(app, '_ctl', side_effect=block), mock.patch.object(app, 'status', return_value={}):
            worker = threading.Thread(target=stop)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(app.ControlBusy):
                    app.set_mode({'mode': 'live', 'target': 'test'})
                with self.assertRaises(app.ControlBusy):
                    app.room({'action': 'stop'})
            finally:
                release.set()
                worker.join(3)
        self.assertFalse(errors)
        with self.assertRaises(ValueError):
            app.set_mode({'mode': 'invalid'})
        self.assertFalse(app.CONTROL_LOCK.locked())

    def test_failed_stop_never_starts_new_mode(self):
        with mock.patch.object(app, 'ensure_room_live'), mock.patch.object(app, '_write_env'), mock.patch.object(app, '_ctl') as ctl, mock.patch.object(app, '_wait_inactive', return_value=False):
            with self.assertRaises(RuntimeError):
                app.set_mode({'mode': 'live', 'target': 'demo', 'force': True})
        ctl.assert_called_once_with('disable', '--now', app.REPLAY_UNIT)

    def test_deactivating_is_not_stopped(self):
        with mock.patch.object(app, '_show', side_effect=[{'active': 'deactivating'}, {'active': 'inactive'}]) as show, mock.patch('time.sleep'):
            self.assertTrue(app._wait_inactive(app.LIVE_UNIT))
            self.assertEqual(show.call_count, 2)

    def test_http_validation_and_busy_response(self):
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with mock.patch.object(app.Handler, 'log_message'), mock.patch.object(app, 'stop_all', return_value={'ok': True}) as stop:
                for body in ('[]', 'null', '"text"'):
                    conn = http.client.HTTPConnection(*server.server_address, timeout=2)
                    conn.request('POST', '/api/stop', body, {'Content-Type': 'application/json'})
                    resp = conn.getresponse()
                    self.assertEqual(resp.status, 400)
                    self.assertIn('error', json.loads(resp.read()))
                    conn.close()
                stop.assert_not_called()
            with mock.patch.object(app.Handler, 'log_message'), mock.patch.object(app, 'stop_all', side_effect=app.ControlBusy('busy')):
                conn = http.client.HTTPConnection(*server.server_address, timeout=2)
                conn.request('POST', '/api/stop', '{}')
                resp = conn.getresponse()
                self.assertEqual(resp.status, 409)
                resp.read()
                conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


class TargetMonitorTest(IsolatedConfigTest):
    """固定目标的开播监测：只改状态快照或推流单元，绝不碰真实服务与网络。"""

    UNIT = {'active': 'active', 'sub': 'running', 'pid': 100, 'pushing': False}
    OFF = {'active': 'inactive', 'sub': 'dead', 'pid': 0, 'pushing': False}

    def setUp(self):
        super().setUp()
        root = Path(self.tmp.name)
        self.live_env, self.auto_env = app.LIVE_ENV, app.AUTO_ENV
        patcher = mock.patch.object(app, '_monitor_state', dict(app._monitor_state))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.live_env.write_text('TARGET=streamer_1\n')
        self.auto_env.write_text('AUTO=1\n')

    def units(self, live=None, replay=None):
        return {app.LIVE_UNIT: dict(live or self.OFF), app.REPLAY_UNIT: dict(replay or self.OFF)}

    def test_offline_probe_reports_reason_and_keeps_unit(self):
        """未开播只更新状态：单次失败可能是抖动，不能立刻动推流单元。"""
        with mock.patch.object(app, '_show_many', return_value=self.units()), \
                mock.patch.object(app, '_pushing', return_value={0: False}), \
                mock.patch.object(app, 'probe_target', return_value=('', 'not currently live')) as probe, \
                mock.patch.object(app, '_ctl') as ctl:
            app.monitor_cycle()
        state = app.target_status()
        self.assertFalse(state['live'])
        self.assertEqual(state['detail'], 'not currently live')
        self.assertEqual(state['streak'], 1)
        self.assertEqual(state['target'], 'streamer_1')
        probe.assert_called_once_with('streamer_1')
        ctl.assert_not_called()

    def test_second_offline_check_stops_push(self):
        with mock.patch.object(app, '_show_many', return_value=self.units(live=self.UNIT)), \
                mock.patch.object(app, '_pushing', return_value={100: False}), \
                mock.patch.object(app, 'probe_target', return_value=('', 'offline')), \
                mock.patch.object(app, '_ctl') as ctl:
            app.monitor_cycle()
            ctl.assert_not_called()
            app.monitor_cycle()
        ctl.assert_called_once_with('disable', '--now', app.LIVE_UNIT)

    def test_live_probe_starts_push_when_armed(self):
        with mock.patch.object(app, '_show_many', return_value=self.units()), \
                mock.patch.object(app, '_pushing', return_value={0: False}), \
                mock.patch.object(app, 'probe_target', return_value=('https://live.flv', '已开播')), \
                mock.patch.object(app, 'ensure_room_live') as room, \
                mock.patch.object(app, 'run') as run, \
                mock.patch.object(app, '_ctl') as ctl:
            app.monitor_cycle()
        room.assert_called_once_with()
        self.assertIn('TARGET=streamer_1', self.live_env.read_text())
        self.assertEqual([c.args for c in ctl.call_args_list],
                         [('enable', app.LIVE_UNIT), ('restart', app.LIVE_UNIT)])
        run.assert_called_once()  # reset-failed
        self.assertTrue(app.target_status()['live'])

    def test_live_probe_does_not_start_when_disarmed(self):
        """用户明确停掉后开播也不能被拉回来。"""
        self.auto_env.write_text('AUTO=0\n')
        with mock.patch.object(app, '_show_many', return_value=self.units()), \
                mock.patch.object(app, '_pushing', return_value={0: False}), \
                mock.patch.object(app, 'probe_target', return_value=('https://live.flv', '已开播')), \
                mock.patch.object(app, '_ctl') as ctl:
            app.monitor_cycle()
        ctl.assert_not_called()
        self.assertTrue(app.target_status()['live'])  # 状态照样展示

    def test_ffmpeg_pushing_skips_tiktok_probe(self):
        with mock.patch.object(app, '_show_many', return_value=self.units(live=self.UNIT)), \
                mock.patch.object(app, '_pushing', return_value={100: True}), \
                mock.patch.object(app, 'probe_target') as probe:
            app.monitor_cycle()
        probe.assert_not_called()
        state = app.target_status()
        self.assertTrue(state['live'])
        self.assertEqual(state['source'], 'push')

    def test_replay_running_is_never_hijacked(self):
        """两种模式互斥是硬约束：轮播在跑时监测只报状态，不抢单元。"""
        with mock.patch.object(app, '_show_many', return_value=self.units(replay=self.UNIT)), \
                mock.patch.object(app, '_pushing', return_value={0: False, 100: True}), \
                mock.patch.object(app, 'probe_target') as probe, \
                mock.patch.object(app, '_ctl') as ctl:
            app.monitor_cycle()
        probe.assert_not_called()
        ctl.assert_not_called()
        self.assertIsNone(app.target_status()['live'])

    def test_stuck_replay_unit_also_blocks_takeover(self):
        """轮播 ffmpeg 已死但单元还 active：抢单元就变双推流，仍让路。"""
        with mock.patch.object(app, '_show_many', return_value=self.units(replay=self.UNIT)), \
                mock.patch.object(app, '_pushing', return_value={0: False, 100: False}), \
                mock.patch.object(app, 'probe_target') as probe, \
                mock.patch.object(app, '_ctl') as ctl:
            app.monitor_cycle()
        probe.assert_not_called()
        ctl.assert_not_called()

    def test_switching_target_clears_offline_streak(self):
        """换人后第一次失败不算连续：旧目标的账不能带过去。"""
        with mock.patch.object(app, '_show_many', return_value=self.units(live=self.UNIT)), \
                mock.patch.object(app, '_pushing', return_value={100: False}), \
                mock.patch.object(app, 'probe_target', return_value=('', 'offline')), \
                mock.patch.object(app, '_ctl'):
            app.monitor_cycle()
            app.monitor_cycle()
            self.assertEqual(app.target_status()['streak'], 2)
            self.live_env.write_text('TARGET=streamer_2\n')
            app.monitor_cycle()
        self.assertEqual(app.target_status()['streak'], 1)

    def test_missing_target_reports_unknown(self):
        self.live_env.write_text('TARGET=\n')
        with mock.patch.object(app, '_show_many') as show:
            app.monitor_cycle()
        show.assert_not_called()
        state = app.target_status()
        self.assertIsNone(state['live'])
        self.assertIn('未设置目标', state['detail'])

    def test_stop_all_and_room_stop_disarm_watchdog(self):
        with mock.patch.object(app, '_ctl'), mock.patch.object(app, 'status', return_value={}):
            app.stop_all()
        self.assertFalse(app.auto_armed())
        with mock.patch.object(app, '_ctl'), mock.patch.object(app, 'run',
                  return_value=type('R', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()), \
                mock.patch.object(app, 'status', return_value={}):
            app.room({'action': 'stop'})
        self.assertFalse(app.auto_armed())

    def test_switch_to_replay_disarms_watchdog(self):
        path = Path(self.tmp.name) / 'clip.mp4'
        path.write_bytes(b'0')
        with mock.patch.object(app, 'ensure_room_live'), mock.patch.object(app, '_wait_inactive', return_value=True), \
                mock.patch.object(app, 'run'), mock.patch.object(app, '_ctl'), \
                mock.patch.object(app, 'status', return_value={}):
            app.set_mode({'mode': 'replay', 'paths': [str(path)]})
        self.assertFalse(app.auto_armed())
        self.assertIn(str(path), (Path(self.tmp.name) / 'replay.env').read_text())  # 落在临时目录

    def test_auto_control_yields_to_user_operation(self):
        app.CONTROL_LOCK.acquire()
        try:
            self.assertFalse(app._auto_control(lambda: self.fail('不该被执行')))
        finally:
            app.CONTROL_LOCK.release()

    def test_probe_target_surfaces_failure_reason(self):
        failed = type('R', (), {'returncode': 1, 'stdout': '', 'stderr': 'detail\n未开播\n'})()
        with mock.patch.object(app, 'run', return_value=failed):
            self.assertEqual(app.probe_target('who'), ('', '未开播'))
        timed_out = subprocess.TimeoutExpired(cmd='x', timeout=1)
        with mock.patch.object(app, 'run', side_effect=timed_out):
            url, detail = app.probe_target('who')
        self.assertEqual(url, '')
        self.assertIn('超时', detail)


if __name__ == '__main__':
    unittest.main()
