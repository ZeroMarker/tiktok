"""值守守护进程 monitord 测试：只改状态快照或推流单元，绝不碰真实服务与网络。"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import monitord  # noqa: E402
import pushctl as ctl  # noqa: E402
from test_webui import isolate_config  # noqa: E402


class TargetMonitorTest(unittest.TestCase):
    """固定目标的开播监测：只改状态快照或推流单元，绝不碰真实服务与网络。"""

    UNIT = {'active': 'active', 'sub': 'running', 'pid': 100, 'pushing': False}
    OFF = {'active': 'inactive', 'sub': 'dead', 'pid': 0, 'pushing': False}

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate_config(self, Path(self.tmp.name))
        self.live_env, self.auto_env = ctl.LIVE_ENV, ctl.AUTO_ENV
        patcher = mock.patch.object(monitord, 'state', dict(monitord.state))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.live_env.write_text('TARGET=streamer_1\n')
        self.auto_env.write_text('AUTO=1\n')

    def units(self, live=None, replay=None):
        return {ctl.LIVE_UNIT: dict(live or self.OFF), ctl.REPLAY_UNIT: dict(replay or self.OFF)}

    def test_offline_probe_reports_reason_and_keeps_unit(self):
        """未开播只更新状态：单次失败可能是抖动，不能立刻动推流单元。"""
        with mock.patch.object(ctl, 'show_many', return_value=self.units()), \
                mock.patch.object(ctl, 'pushing', return_value={0: False}), \
                mock.patch.object(ctl, 'probe_target', return_value=('', 'not currently live')) as probe, \
                mock.patch.object(ctl, 'ctl') as systemctl:
            monitord.cycle()
        state = monitord.state
        self.assertFalse(state['live'])
        self.assertEqual(state['detail'], 'not currently live')
        self.assertEqual(state['streak'], 1)
        self.assertEqual(state['target'], 'streamer_1')
        probe.assert_called_once_with('streamer_1')
        systemctl.assert_not_called()

    def test_second_offline_check_stops_push(self):
        with mock.patch.object(ctl, 'show_many', return_value=self.units(live=self.UNIT)), \
                mock.patch.object(ctl, 'pushing', return_value={100: False}), \
                mock.patch.object(ctl, 'probe_target', return_value=('', 'offline')), \
                mock.patch.object(ctl, 'ctl') as systemctl, \
                mock.patch.object(ctl, 'wait_inactive', return_value=True), \
                mock.patch.object(ctl, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
            monitord.cycle()
            systemctl.assert_not_called()
            run.assert_not_called()
            monitord.cycle()
        systemctl.assert_called_once_with('disable', '--now', ctl.LIVE_UNIT)
        run.assert_called_once_with(['python3', str(ctl.LIVE_PY), 'stop'], timeout=60, check=False)
        self.assertTrue(ctl.auto_armed())
        self.assertFalse(monitord.state['close_pending'])

    def test_failed_room_close_retries_after_push_stopped(self):
        with mock.patch.object(ctl, 'ctl'), \
                mock.patch.object(ctl, 'wait_inactive', return_value=True), \
                mock.patch.object(ctl, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'failed')):
            with self.assertRaises(RuntimeError):
                monitord.stop_offline_live()
        self.assertTrue(monitord.state['close_pending'])
        with mock.patch.object(ctl, 'show_many', return_value=self.units()), \
                mock.patch.object(ctl, 'pushing', return_value={0: False}), \
                mock.patch.object(ctl, 'probe_target', return_value=('', 'offline')), \
                mock.patch.object(ctl, 'ctl'), \
                mock.patch.object(ctl, 'wait_inactive', return_value=True), \
                mock.patch.object(ctl, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as run:
            monitord.cycle()
            monitord.cycle()
        run.assert_called_once()
        self.assertFalse(monitord.state['close_pending'])
        self.assertTrue(ctl.auto_armed())

    def test_live_probe_starts_push_when_armed(self):
        with mock.patch.object(ctl, 'show_many', return_value=self.units()), \
                mock.patch.object(ctl, 'pushing', return_value={0: False}), \
                mock.patch.object(ctl, 'probe_target', return_value=('https://live.flv', '已开播')), \
                mock.patch.object(ctl, 'ensure_room_live') as room, \
                mock.patch.object(ctl, 'run') as run, \
                mock.patch.object(ctl, 'ctl') as systemctl:
            monitord.cycle()
        room.assert_called_once_with()
        self.assertIn('TARGET=streamer_1', self.live_env.read_text())
        self.assertEqual([c.args for c in systemctl.call_args_list],
                         [('enable', ctl.LIVE_UNIT), ('restart', ctl.LIVE_UNIT)])
        run.assert_called_once()  # reset-failed
        self.assertTrue(monitord.state['live'])

    def test_running_retry_loop_recovers_closed_room(self):
        for reopened in (False, True):
            with self.subTest(reopened=reopened), \
                    mock.patch.object(ctl, 'show_many', return_value=self.units(live=self.UNIT)), \
                    mock.patch.object(ctl, 'pushing', return_value={100: False}), \
                    mock.patch.object(ctl, 'probe_target', return_value=('https://live.flv', '已开播')), \
                    mock.patch.object(ctl, 'ensure_room_live', return_value=reopened) as room, \
                    mock.patch.object(ctl, 'ctl') as systemctl:
                monitord.cycle()
                room.assert_called_once_with()
                if reopened:
                    systemctl.assert_called_once_with('restart', ctl.LIVE_UNIT)
                else:
                    systemctl.assert_not_called()

    def test_running_retry_loop_does_not_reopen_when_disarmed(self):
        self.auto_env.write_text('AUTO=0\n')
        with mock.patch.object(ctl, 'show_many', return_value=self.units(live=self.UNIT)), \
                mock.patch.object(ctl, 'pushing', return_value={100: False}), \
                mock.patch.object(ctl, 'probe_target', return_value=('https://live.flv', '已开播')), \
                mock.patch.object(ctl, 'ensure_room_live') as room:
            monitord.cycle()
        room.assert_not_called()

    def test_live_probe_does_not_start_when_disarmed(self):
        """用户明确停掉后开播也不能被拉回来。"""
        self.auto_env.write_text('AUTO=0\n')
        with mock.patch.object(ctl, 'show_many', return_value=self.units()), \
                mock.patch.object(ctl, 'pushing', return_value={0: False}), \
                mock.patch.object(ctl, 'probe_target', return_value=('https://live.flv', '已开播')), \
                mock.patch.object(ctl, 'ctl') as systemctl:
            monitord.cycle()
        systemctl.assert_not_called()
        self.assertTrue(monitord.state['live'])  # 状态照样展示

    def test_ffmpeg_pushing_skips_tiktok_probe(self):
        with mock.patch.object(ctl, 'show_many', return_value=self.units(live=self.UNIT)), \
                mock.patch.object(ctl, 'pushing', return_value={100: True}), \
                mock.patch.object(ctl, 'probe_target') as probe:
            monitord.cycle()
        probe.assert_not_called()
        state = monitord.state
        self.assertTrue(state['live'])
        self.assertEqual(state['source'], 'push')

    def test_replay_running_is_never_hijacked(self):
        """两种模式互斥是硬约束：轮播在跑时监测只报状态，不抢单元。"""
        with mock.patch.object(ctl, 'show_many', return_value=self.units(replay=self.UNIT)), \
                mock.patch.object(ctl, 'pushing', return_value={0: False, 100: True}), \
                mock.patch.object(ctl, 'probe_target') as probe, \
                mock.patch.object(ctl, 'ctl') as systemctl:
            monitord.cycle()
        probe.assert_not_called()
        systemctl.assert_not_called()
        self.assertIsNone(monitord.state['live'])

    def test_stuck_replay_unit_also_blocks_takeover(self):
        """轮播 ffmpeg 已死但单元还 active：抢单元就变双推流，仍让路。"""
        with mock.patch.object(ctl, 'show_many', return_value=self.units(replay=self.UNIT)), \
                mock.patch.object(ctl, 'pushing', return_value={0: False, 100: False}), \
                mock.patch.object(ctl, 'probe_target') as probe, \
                mock.patch.object(ctl, 'ctl') as systemctl:
            monitord.cycle()
        probe.assert_not_called()
        systemctl.assert_not_called()

    def test_switching_target_clears_offline_streak(self):
        """换人后第一次失败不算连续：旧目标的账不能带过去。"""
        with mock.patch.object(ctl, 'show_many', return_value=self.units(live=self.UNIT)), \
                mock.patch.object(ctl, 'pushing', return_value={100: False}), \
                mock.patch.object(ctl, 'probe_target', return_value=('', 'offline')), \
                mock.patch.object(monitord, 'stop_offline_live'):
            monitord.cycle()
            monitord.cycle()
            self.assertEqual(monitord.state['streak'], 2)
            self.live_env.write_text('TARGET=streamer_2\n')
            monitord.cycle()
        self.assertEqual(monitord.state['streak'], 1)

    def test_missing_target_reports_unknown(self):
        self.live_env.write_text('TARGET=\n')
        with mock.patch.object(ctl, 'show_many') as show:
            monitord.cycle()
        show.assert_not_called()
        state = monitord.state
        self.assertIsNone(state['live'])
        self.assertIn('未设置目标', state['detail'])

    def test_auto_control_yields_to_user_operation(self):
        with ctl.control_lock():  # 管理页正在执行用户操作
            self.assertFalse(monitord.auto_control(lambda: self.fail('不该被执行')))

    def test_probe_target_surfaces_failure_reason(self):
        failed = type('R', (), {'returncode': 1, 'stdout': '', 'stderr': 'detail\n未开播\n'})()
        with mock.patch.object(ctl, 'run', return_value=failed):
            self.assertEqual(ctl.probe_target('who'), ('', '未开播'))
        timed_out = subprocess.TimeoutExpired(cmd='x', timeout=1)
        with mock.patch.object(ctl, 'run', side_effect=timed_out):
            url, detail = ctl.probe_target('who')
        self.assertEqual(url, '')
        self.assertIn('超时', detail)



class MonitorStateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate_config(self, Path(self.tmp.name))
        patcher = mock.patch.object(monitord, 'state', dict(monitord.state))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_every_cycle_persists_snapshot(self):
        ctl.write_env(ctl.LIVE_ENV, ['TARGET='])
        monitord.cycle()
        saved = ctl.read_monitor_state()
        self.assertIsNone(saved['live'])
        self.assertIn('未设置目标', saved['detail'])
        self.assertGreater(saved['next_at'], saved['checked_at'])

    def test_restart_keeps_streak_and_pending_close(self):
        ctl.write_monitor_state({'target': 'a', 'streak': 1, 'epoch': 'e', 'close_pending': True, 'live': True})
        monitord.load_state()
        self.assertEqual((monitord.state['streak'], monitord.state['close_pending']), (1, True))
        self.assertIsNone(monitord.state['live'])  # 「在播」这类瞬时结论不跨重启沿用

    def test_new_arm_epoch_clears_streak(self):
        ctl.write_env(ctl.LIVE_ENV, ['TARGET=streamer_1'])
        ctl.set_armed(True)
        off = {'active': 'inactive', 'sub': 'dead', 'pid': 0}
        with mock.patch.object(ctl, 'show_many', return_value={ctl.LIVE_UNIT: off, ctl.REPLAY_UNIT: off}), \
                mock.patch.object(ctl, 'probe_target', return_value=('', 'offline')):
            monitord.cycle()
            self.assertEqual(monitord.state['streak'], 1)
            ctl.set_armed(True)  # 用户在管理页重新开值守
            monitord.cycle()
        self.assertEqual(monitord.state['streak'], 1)


if __name__ == '__main__':
    unittest.main()
