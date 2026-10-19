"""WebUI regression tests: no real services, credentials or upstream requests."""
import http.client
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

spec = importlib.util.spec_from_file_location('webui_app', Path(__file__).resolve().parents[1] / 'webui/app.py')
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ctl = app.ctl  # 与 monitord 共用的 pushctl 模块对象


def isolate_config(case, root: Path) -> None:
    """配置目录隔离：任何用例写 live/replay/auto.env、锁和快照都落在临时目录，不碰线上配置。"""
    overrides = {'CONFIG_DIR': root, 'LIVE_ENV': root / 'live.env', 'REPLAY_ENV': root / 'replay.env',
                 'AUTO_ENV': root / 'auto.env', 'PUSH_ENV': root / 'push.env',
                 'CONTROL_LOCK_FILE': root / 'control.lock', 'MONITOR_STATE_FILE': root / 'monitord.json'}
    for name, value in overrides.items():
        patcher = mock.patch.object(ctl, name, value)
        patcher.start()
        case.addCleanup(patcher.stop)


class IsolatedConfigTest(unittest.TestCase):
    """配置目录隔离：任何用例写 live/replay/auto.env 都落在临时目录，不碰线上配置。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        isolate_config(self, Path(self.tmp.name))


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
                    mock.patch.object(ctl, 'CONFIG_DIR', config), mock.patch.object(ctl, 'PUSH_ENV', output), mock.patch.object(ctl, 'SESSION_FILE', session):
                ctl.sync_push_env()
                ctl.sync_push_env()
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
                    mock.patch.object(ctl, 'SESSION_FILE', root / 'missing-legacy.json'):
                self.assertEqual(ctl.session_file(), live)
                # 切走 live 默认账号后 WebUI 应跟随
                (accounts / 'defaults.json').write_text(json.dumps({'live': 'upload'}))
                self.assertEqual(ctl.session_file(), accounts / 'upload.json')

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
        with mock.patch.object(ctl, 'ctl', side_effect=block), mock.patch.object(app, '_nudge_monitor'), \
                mock.patch.object(app, 'status', return_value={}):
            worker = threading.Thread(target=stop)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                with self.assertRaises(ctl.ControlBusy):
                    app.set_mode({'mode': 'live', 'target': 'test'})
                with self.assertRaises(ctl.ControlBusy):
                    app.room({'action': 'stop'})
            finally:
                release.set()
                worker.join(3)
        self.assertFalse(errors)
        with self.assertRaises(ValueError):
            app.set_mode({'mode': 'invalid'})
        with ctl.control_lock():  # 锁已释放
            pass

    def test_failed_stop_never_starts_new_mode(self):
        with mock.patch.object(ctl, 'ensure_room_live'), mock.patch.object(ctl, 'write_env'), mock.patch.object(ctl, 'ctl') as systemctl, mock.patch.object(ctl, 'wait_inactive', return_value=False):
            with self.assertRaises(RuntimeError):
                app.set_mode({'mode': 'live', 'target': 'demo', 'force': True})
        systemctl.assert_called_once_with('disable', '--now', app.REPLAY_UNIT)

    def test_deactivating_is_not_stopped(self):
        with mock.patch.object(ctl, 'show', side_effect=[{'active': 'deactivating'}, {'active': 'inactive'}]) as show, mock.patch('time.sleep'):
            self.assertTrue(ctl.wait_inactive(app.LIVE_UNIT))
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
            with mock.patch.object(app.Handler, 'log_message'), mock.patch.object(app, 'stop_all', side_effect=ctl.ControlBusy('busy')):
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


class FrontendModuleGraphTest(unittest.TestCase):
    """Lit + Material Web、无构建链：import map 与相对引用必须都能解析到真实文件。"""

    WEBUI = app.WEBUI_DIR
    FRONTEND = app.WEBUI_DIR / 'frontend'
    VENDOR = app.WEBUI_DIR / 'vendor'
    IMPORT_SPEC = re.compile(r"""(?:from|import)\s*['"]([^'"]+)['"]""")

    def setUp(self):
        self.shell = app.INDEX_FILE.read_text(encoding='utf-8')
        match = re.search(r'<script type="importmap">(.*?)</script>', self.shell, re.S)
        self.assertIsNotNone(match, '壳页面必须提供静态 import map')
        self.imports = json.loads(match.group(1))['imports']

    def sources(self):
        return [*self.FRONTEND.rglob('*.js'), *self.VENDOR.rglob('*.js')]

    def test_shell_assets_exist(self):
        self.assertIn('./frontend/main.js', self.shell)
        for name, target in self.imports.items():
            self.assertTrue(target.startswith('./vendor/'), f'{name} 必须指向本地 vendor：{target}')
            resolved = (self.WEBUI / target[2:])
            self.assertTrue(resolved.is_dir() if target.endswith('/') else resolved.is_file(), f'{name} -> {target}')

    def test_relative_imports_resolve(self):
        for path in self.sources():
            for spec in self.IMPORT_SPEC.findall(path.read_text(encoding='utf-8')):
                if spec.startswith('.'):
                    self.assertTrue((path.parent / spec).resolve().is_file(), f'{path.relative_to(self.WEBUI)} -> {spec}')

    def test_bare_imports_are_mapped(self):
        for path in self.sources():
            for spec in self.IMPORT_SPEC.findall(path.read_text(encoding='utf-8')):
                if spec.startswith('.'):
                    continue
                ok = spec in self.imports or any(k.endswith('/') and spec.startswith(k) for k in self.imports)
                self.assertTrue(ok, f'{path.relative_to(self.WEBUI)} -> {spec} 不在 import map 中')

    def test_no_cdn_references(self):
        for path in [app.INDEX_FILE, *self.FRONTEND.rglob('*.js')]:
            self.assertNotRegex(path.read_text(encoding='utf-8'), r'https?://(?!127\.0\.0\.1)', path.name)

    def test_every_component_is_registered_and_used(self):
        main = (self.FRONTEND / 'main.js').read_text(encoding='utf-8')
        for path in (self.FRONTEND / 'components').glob('*.js'):
            self.assertIn(f'./components/{path.name}', main)
            self.assertIn(f'customElements.define("{path.stem}"', path.read_text(encoding='utf-8'))

    def test_vendor_identical_to_recorder_webui(self):
        """与录制中心 webui/vendor 同一份文件：升级时漏同步一边会在这里暴露。"""
        other = PROJECT_ROOT.parent / 'webui' / 'vendor'
        if not other.is_dir():
            self.skipTest('不在主仓库中')
        mine = {p.relative_to(self.VENDOR): p.read_bytes() for p in self.VENDOR.rglob('*') if p.is_file()}
        theirs = {p.relative_to(other): p.read_bytes() for p in other.rglob('*') if p.is_file()}
        self.assertEqual(mine.keys() - {Path('README.md')}, theirs.keys() - {Path('README.md')})
        for rel, data in mine.items():
            if rel != Path('README.md'):
                self.assertEqual(data, theirs[rel], str(rel))

    def test_service_worker_precache_entries_exist(self):
        sw = (self.WEBUI / 'sw.js').read_text(encoding='utf-8')
        shell = re.search(r'const SHELL = \[(.*?)\];', sw, re.S).group(1)
        for url in re.findall(r'"(/[^"]*)"', shell):
            if url == '/':
                continue
            path = app.PWA_STATIC.get(url, (None,))[0] or (tree := app.resolve_static_tree(url)) and tree[0]
            self.assertTrue(path and Path(path).is_file(), url)


class StaticTreeTest(unittest.TestCase):
    def test_serves_frontend_and_vendor(self):
        for url in ('/frontend/main.js', '/vendor/lit/index.js', '/vendor/material-web/dialog/dialog.js'):
            path, ctype, _ = app.resolve_static_tree(url)
            self.assertTrue(path.is_file(), url)
            self.assertTrue(ctype.startswith('text/javascript'), url)

    def test_rejects_traversal_and_other_files(self):
        for url in ('/frontend/../app.py', '/vendor/../app.py', '/frontend/', '/vendor/README.md',
                    '/frontend/../../pushctl.py', '/frontend/__pycache__/x.pyc'):
            self.assertIsNone(app.resolve_static_tree(url), url)


class WebUIControlTest(IsolatedConfigTest):
    """管理页只做用户操作 + 读值守快照，不自己跑值守。"""

    def test_stop_all_and_room_stop_disarm_watchdog(self):
        with mock.patch.object(ctl, 'ctl'), mock.patch.object(app, '_nudge_monitor'), \
                mock.patch.object(app, 'status', return_value={}):
            app.stop_all()
        self.assertFalse(ctl.auto_armed())
        ctl.set_armed(True)
        with mock.patch.object(ctl, 'ctl'), mock.patch.object(app, '_nudge_monitor'), mock.patch.object(ctl, 'run',
                  return_value=type('R', (), {'returncode': 0, 'stdout': '', 'stderr': ''})()), \
                mock.patch.object(app, 'status', return_value={}):
            app.room({'action': 'stop'})
        self.assertFalse(ctl.auto_armed())

    def test_switch_to_replay_disarms_watchdog(self):
        path = Path(self.tmp.name) / 'clip.mp4'
        path.write_bytes(b'0')
        with mock.patch.object(ctl, 'ensure_room_live'), mock.patch.object(ctl, 'wait_inactive', return_value=True), \
                mock.patch.object(ctl, 'run'), mock.patch.object(ctl, 'ctl'), \
                mock.patch.object(app, 'status', return_value={}):
            app.set_mode({'mode': 'replay', 'paths': [str(path)]})
        self.assertFalse(ctl.auto_armed())
        self.assertIn(str(path), (Path(self.tmp.name) / 'replay.env').read_text())  # 落在临时目录

    def test_switch_to_live_arms_with_new_epoch(self):
        """每次开值守都是新纪元：monitord 据此清零旧的连续下播计数。"""
        with mock.patch.object(ctl, 'ensure_room_live'), mock.patch.object(ctl, 'wait_inactive', return_value=True), \
                mock.patch.object(ctl, 'run'), mock.patch.object(ctl, 'ctl'), mock.patch.object(app, '_nudge_monitor'), \
                mock.patch.object(app, 'status', return_value={}):
            app.set_mode({'mode': 'live', 'target': 'demo', 'force': True})
            first = ctl.arm_epoch()
            app.set_mode({'mode': 'live', 'target': 'demo', 'force': True})
        self.assertTrue(ctl.auto_armed())
        self.assertTrue(first)
        self.assertNotEqual(first, ctl.arm_epoch())

    def test_target_status_reads_monitor_snapshot(self):
        ctl.write_env(ctl.LIVE_ENV, ['TARGET=streamer_1'])
        ctl.write_monitor_state({'live': True, 'detail': '已开播', 'source': 'probe', 'streak': 0,
                                 'checked_at': 1.0, 'next_at': 0.0})
        with mock.patch.object(ctl, 'show', return_value={'active': 'active'}):
            state = app.target_status()
        self.assertTrue(state['live'])
        self.assertEqual(state['target'], 'streamer_1')
        self.assertTrue(state['monitor'])

    def test_target_status_when_monitor_down_is_unknown(self):
        """值守没在跑：旧快照不能冒充当前状态。"""
        ctl.write_monitor_state({'live': True, 'detail': '已开播', 'checked_at': 1.0})
        with mock.patch.object(ctl, 'show', return_value={'active': 'inactive'}):
            state = app.target_status()
        self.assertIsNone(state['live'])
        self.assertIn('未运行', state['detail'])
        self.assertFalse(state['monitor'])

    def test_request_probe_signals_monitor_and_waits_for_new_snapshot(self):
        ctl.write_monitor_state({'checked_at': 1.0})

        def fake_ctl(*args):
            ctl.write_monitor_state({'checked_at': 2.0})  # monitord 收到信号后写新快照
        with mock.patch.object(ctl, 'ctl', side_effect=fake_ctl) as systemctl:
            self.assertTrue(app.request_probe(wait=2))
        systemctl.assert_called_once_with('kill', '-s', 'USR1', '--kill-whom=main', app.MONITOR_UNIT)

    def test_webui_has_no_monitor_loop(self):
        """前后端分离：值守逻辑只在 monitord，管理页进程里不能再有监测线程。"""
        for name in ('monitor_cycle', 'monitor_loop', '_record', '_auto_control'):
            self.assertFalse(hasattr(app, name), name)


if __name__ == '__main__':
    unittest.main()
