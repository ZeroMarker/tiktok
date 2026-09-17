import io
import json
import os
import re
import shutil
import tempfile
import unittest
from http import HTTPStatus
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from webui import app

# 所有用例都在临时任务目录上运行：start_job 会持久化启动参数（state/tasks.json，
# 供「暂停/继续」使用），未隔离时会把测试数据写进真实部署目录。
_STATE_DIR = tempfile.TemporaryDirectory(prefix="webui_test_state_")
_STATE_PATCHES = [
    patch.object(app, "STATE_DIR", Path(_STATE_DIR.name)),
    patch.object(app, "CATALOG_FILE", Path(_STATE_DIR.name) / "tasks.json"),
]


def setUpModule() -> None:
    for patcher in _STATE_PATCHES:
        patcher.start()
    unittest.addModuleCleanup(_STATE_DIR.cleanup)


def tearDownModule() -> None:
    for patcher in _STATE_PATCHES:
        patcher.stop()


class _FakeHandler(app.Handler):
    """Minimal HTTP handler that skips socket setup (unit-testable do_GET)."""

    def __init__(self, path: str, token: str = "") -> None:
        self.path = path
        self.command = "GET"
        self.protocol_version = "HTTP/1.1"
        self.request_version = "HTTP/1.1"
        self.headers = {"X-Auth-Token": token}
        self.requestline = f"GET {path} HTTP/1.1"
        self.wfile = io.BytesIO()
        self.rfile = io.BytesIO()
        self._headers_buffer = []
        self.close_connection = True
        self.server_version = app.Handler.server_version
        self.sys_version = "test"
        self.log_message = lambda *args: None  # silence request logging

    def send_error(self, code: int, *args, **kwargs) -> None:  # pragma: no cover
        self.send_response_only(code)
        self.end_headers()


class WebUIHTTPTest(unittest.TestCase):
    def _get(self, path: str, token: str = "") -> tuple[int, str, bytes]:
        handler = _FakeHandler(path, token)
        handler.do_GET()
        raw = handler.wfile.getvalue()
        head, _, body = raw.partition(b"\r\n\r\n")
        lines = head.decode("latin-1").splitlines()
        status = int(lines[0].split()[1]) if lines else 0
        content_type = next(
            (l.split(":", 1)[1].strip() for l in lines if l.lower().startswith("content-type")), ""
        )
        return status, content_type, body

    def _post(self, path: str, payload: dict) -> tuple[int, bytes]:
        handler = _FakeHandler(path)
        body = json.dumps(payload).encode()
        handler.command = "POST"
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = io.BytesIO(body)
        handler.do_POST()
        raw = handler.wfile.getvalue()
        head, _, response = raw.partition(b"\r\n\r\n")
        status = int(head.decode("latin-1").splitlines()[0].split()[1]) if head else 0
        return status, response

    def test_manifest_served_with_pwa_mime(self):
        status, content_type, body = self._get("/manifest.webmanifest")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("application/manifest+json", content_type)
        self.assertIn(b'"start_url"', body)

    def test_service_worker_served_as_javascript(self):
        status, content_type, _ = self._get("/sw.js")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("javascript", content_type)

    def test_icons_and_favicon_served(self):
        for name, mime in [
            ("icon-32.png", "image/png"),
            ("icon-192.png", "image/png"),
            ("icon-512.png", "image/png"),
            ("icon-maskable-512.png", "image/png"),
            ("favicon.ico", "image/x-icon"),
        ]:
            status, content_type, body = self._get(f"/{name}")
            self.assertEqual(status, HTTPStatus.OK, name)
            self.assertEqual(content_type, mime, name)
            self.assertEqual(body, (app.WEBUI_DIR / name).read_bytes(), name)

    def test_index_alias_served(self):
        status, content_type, _ = self._get("/index.html")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertIn("text/html", content_type)

    def test_unknown_path_is_404(self):
        status, _, _ = self._get("/nope")
        self.assertEqual(status, HTTPStatus.NOT_FOUND)

    def test_manifest_icons_are_valid(self):

        manifest = json.loads((app.WEBUI_DIR / "manifest.webmanifest").read_text())
        self.assertTrue(manifest["start_url"])
        purposes = {icon["purpose"] for icon in manifest["icons"]}
        self.assertIn("maskable", purposes)
        self.assertTrue(all((app.WEBUI_DIR / icon["src"]).is_file() for icon in manifest["icons"]))

    def test_api_requires_no_auth_token(self):

        # 认证已移除：无令牌请求必须被放行。
        status, content_type, body = self._get("/api/health")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(json.loads(body)["ok"], True)

    def test_api_jobs_without_token_is_allowed(self):

        with patch.object(app, "list_jobs", return_value=[]):
            status, _, body = self._get("/api/jobs")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(json.loads(body), [])

    def test_api_works_when_token_env_is_empty(self):
        # 即便环境变量为空，服务也能启动并响应（不再要求非空令牌）。
        with patch.dict(os.environ, {"LIVE_WEBUI_TOKEN": ""}, clear=False):
            handler = _FakeHandler("/api/health")
            handler.do_GET()
            self.assertEqual(handler.wfile.getvalue().split(b"\r\n")[0], b"HTTP/1.1 200 OK")

    def test_dynamic_values_are_not_interpolated_into_inline_handlers(self):
        # Vue 应用使用事件绑定而非内联 onclick="..." 拼接用户数据，防范持久型 XSS。
        index = app.INDEX_FILE.read_text(encoding="utf-8")
        self.assertNotIn("onclick=", index)
        self.assertNotIn("onerror=", index)
        self.assertNotIn("javascript:", index)
        self.assertIn("createApp", index)
        self.assertIn("#app", index)

    def test_webui_has_persistent_snapshot_and_refresh_feedback(self):
        index = app.INDEX_FILE.read_text(encoding="utf-8")
        self.assertIn("livestream-webui-snapshot-v1", index)
        self.assertIn("localStorage.setItem", index)
        self.assertIn("AbortController", index)
        self.assertIn("api/jobs", index)
        self.assertIn("api/overview", index)
        self.assertIn("serviceWorker", index)


class WebUIHelpersTest(unittest.TestCase):
    def test_unit_name_is_stable_and_safe(self):
        first = app.unit_name("tiktok", "@Some.User/live?a=1")
        self.assertEqual(first, app.unit_name("tiktok", "@Some.User/live?a=1"))
        self.assertRegex(first, r"^livestream-rec-tiktok-[a-z0-9-]+\.service$")

    def test_unit_name_distinguishes_targets(self):
        self.assertNotEqual(app.unit_name("kick", "one"), app.unit_name("kick", "two"))

    def test_start_job_rejects_duplicate_target(self):
        existing = [{"platform": "tiktok", "target": "@Some.User", "unit": "livestream-rec-tiktok-some-user-abc.service"}]
        with patch.object(app, "list_jobs", return_value=existing), \
                patch.object(app, "_live_units", return_value=[]), \
                patch.object(app, "run") as mocked:
            with self.assertRaises(ValueError) as ctx:
                app.start_job({"platform": "tiktok", "target": " @some.user "})
        self.assertIn("已存在", str(ctx.exception))
        # 重复任务不得真的去拉起 systemd 单元
        spawns = [call for call in mocked.call_args_list if app.SYSTEMD_RUN in call.args[0]]
        self.assertEqual(spawns, [])

    def test_start_job_allows_different_case_on_other_platform(self):
        existing = [{"platform": "tiktok", "target": "@Some.User", "unit": "livestream-rec-tiktok-some-user-abc.service"}]
        with patch.object(app, "list_jobs", return_value=existing), \
                patch.object(app, "run", return_value=CompletedProcess([], 0, stdout="", stderr="")):
            unit = app.start_job({"platform": "kick", "target": "@some.user"})
        self.assertTrue(unit.startswith("livestream-rec-kick-"))
    def test_recent_files_uses_configured_recordings_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "channel"
            nested.mkdir()
            video = nested / "clip.mp4"
            video.write_bytes(b"video")
            (nested / "ignored.flv").write_bytes(b"stream")
            with patch.object(app, "RECORDINGS_DIR", directory):
                files = app.recent_files()
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["path"], os.path.join("channel", "clip.mp4"))

    def test_recent_files_handles_missing_directory(self):
        with patch.object(app, "RECORDINGS_DIR", "/definitely/missing/directory"):
            self.assertEqual(app.recent_files(), [])

    def test_list_jobs_uses_one_batch_details_query(self):
        listed = CompletedProcess([], 0, stdout=(
            "livestream-rec-tiktok-one.service loaded active running first\n"
            "livestream-rec-kick-two.service loaded inactive dead second\n"
        ), stderr="")
        shown = CompletedProcess([], 0, stdout=(
            "Id=livestream-rec-tiktok-one.service\nActiveState=active\nSubState=running\n"
            "Description=Live recorder: tiktok one\nMainPID=12\nMemoryCurrent=34\nNRestarts=0\n\n"
            "Id=livestream-rec-kick-two.service\nActiveState=inactive\nSubState=dead\n"
            "Description=Live recorder: kick two\nMainPID=0\nMemoryCurrent=0\nNRestarts=1\n"
        ), stderr="")
        with patch.object(app, "run", side_effect=[listed, shown]) as mocked_run:
            jobs = app.list_jobs()
        self.assertEqual(mocked_run.call_count, 2)
        self.assertEqual([job["target"] for job in jobs], ["one", "two"])

    def test_list_jobs_handles_unset_numeric_properties(self):
        listed = CompletedProcess([], 0, stdout=(
            "livestream-rec-tiktok-one.service loaded inactive dead one\n"
        ), stderr="")
        shown = CompletedProcess([], 0, stdout=(
            "Id=livestream-rec-tiktok-one.service\nActiveState=inactive\nSubState=dead\n"
            "Description=Live recorder: tiktok one\nMainPID=[not set]\n"
            "MemoryCurrent=[not set]\nNRestarts=[not set]\n"
        ), stderr="")
        with patch.object(app, "run", side_effect=[listed, shown]):
            jobs = app.list_jobs()
        self.assertEqual(jobs[0]["pid"], 0)
        self.assertEqual(jobs[0]["memory"], 0)
        self.assertEqual(jobs[0]["restarts"], 0)

    def test_list_jobs_reports_streamer_live_status(self):
        listed = CompletedProcess([], 0, stdout=(
            "livestream-rec-tiktok-one.service loaded active running first\n"
            "livestream-rec-tiktok-two.service loaded active running second\n"
            "livestream-rec-kick-three.service loaded inactive dead third\n"
        ), stderr="")
        shown = CompletedProcess([], 0, stdout=(
            "Id=livestream-rec-tiktok-one.service\nActiveState=active\nSubState=running\n"
            "Description=Live recorder: tiktok one\nMainPID=11\nMemoryCurrent=34\nNRestarts=0\n\n"
            "Id=livestream-rec-tiktok-two.service\nActiveState=active\nSubState=running\n"
            "Description=Live recorder: tiktok two\nMainPID=22\nMemoryCurrent=34\nNRestarts=0\n\n"
            "Id=livestream-rec-kick-three.service\nActiveState=inactive\nSubState=dead\n"
            "Description=Live recorder: kick three\nMainPID=0\nMemoryCurrent=0\nNRestarts=1\n"
        ), stderr="")
        with patch.object(app, "run", side_effect=[listed, shown]), \
                patch.object(app, "_ffmpeg_descendant", side_effect=[True, False]) as probed:
            jobs = app.list_jobs()
        self.assertEqual([job["live"] for job in jobs], ["live", "waiting", "offline"])
        # 非活动单元无需探测进程树（只有活动任务才查 ffmpeg 子进程）
        self.assertEqual([call.args[0] for call in probed.call_args_list], [11, 22])

    def test_live_status_is_unknown_when_process_tree_unavailable(self):
        self.assertEqual(app._live_status("active", 0), "unknown")
        with patch.object(app, "_ffmpeg_descendant", return_value=None):
            self.assertEqual(app._live_status("active", 99), "unknown")
        self.assertEqual(app._live_status("failed", 99), "offline")

    def test_overview_counts_live_and_waiting(self):
        jobs = [
            {"platform": "tiktok", "state": "active", "live": "live"},
            {"platform": "tiktok", "state": "active", "live": "waiting"},
            {"platform": "tiktok", "state": "failed", "live": "offline"},
        ]
        with (
            patch.object(app, "list_jobs", return_value=jobs),
            patch.object(app, "list_files", return_value={"total": 0, "offset": 0, "files": []}),
            patch.object(app, "system_stats", return_value={"load": [0.1, 0.2, 0.3], "mem_total": 1000, "mem_available": 500}),
        ):
            data = app.overview()
        self.assertEqual(data["live"], 1)
        self.assertEqual(data["waiting"], 1)
        self.assertEqual(data["running"], 2)

    def test_list_files_search_and_dirs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tiktok_alpha").mkdir()
            (root / "soop_beta").mkdir()
            recent = root / "tiktok_alpha" / "clip_2.mp4"
            recent.write_bytes(b"new")
            older = root / "tiktok_alpha" / "clip_1.mp4"
            older.write_bytes(b"old")
            other = root / "soop_beta" / "live.mp4"
            other.write_bytes(b"soop")
            # mtime 排序：让 clip_2 最新、live.mp4 次之、clip_1 最旧
            older_ts, recent_ts = 1_700_000_000, 1_700_000_100
            os.utime(older, (older_ts, older_ts))
            os.utime(recent, (recent_ts, recent_ts))
            os.utime(other, (recent_ts - 50, recent_ts - 50))
            with patch.object(app, "RECORDINGS_DIR", directory):
                data = app.list_files()
            self.assertEqual(data["total"], 3)
            self.assertEqual([f["name"] for f in data["files"]], ["clip_2.mp4", "live.mp4", "clip_1.mp4"])
            self.assertEqual(data["files"][0]["dir"], "tiktok_alpha")
            self.assertEqual(data["files"][1]["dir"], "soop_beta")
            with patch.object(app, "RECORDINGS_DIR", directory):
                filtered = app.list_files(query="clip_1")
            self.assertEqual(filtered["total"], 1)
            self.assertEqual(filtered["files"][0]["name"], "clip_1.mp4")

    def test_list_files_pagination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i in range(5):
                (root / f"f{i}.mp4").write_bytes(b"x")
                os.utime(root / f"f{i}.mp4", (1_700_000_000 + i, 1_700_000_000 + i))
            with patch.object(app, "RECORDINGS_DIR", directory):
                page = app.list_files(limit=2, offset=2)
            self.assertEqual(page["total"], 5)
            self.assertEqual([f["name"] for f in page["files"]], ["f2.mp4", "f1.mp4"])

    def test_resolve_recording_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / "outside.mp4"
            outside.write_bytes(b"secret")
            with patch.object(app, "RECORDINGS_DIR", directory):
                self.assertIsNone(app.resolve_recording("../outside.mp4"))
                self.assertIsNone(app.resolve_recording("/etc/passwd"))
                self.assertIsNone(app.resolve_recording(""))
                self.assertIsNone(app.resolve_recording("missing.mp4"))
            (root / "ok.mp4").write_bytes(b"data")
            with patch.object(app, "RECORDINGS_DIR", directory):
                self.assertEqual(app.resolve_recording("ok.mp4").name, "ok.mp4")

    def test_delete_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "gone.mp4").write_bytes(b"data")
            with patch.object(app, "RECORDINGS_DIR", directory):
                app.delete_file("gone.mp4")
                self.assertFalse((root / "gone.mp4").exists())
                with self.assertRaises(ValueError):
                    app.delete_file("../etc/passwd")

    def test_job_logs_tail(self):
        with patch.object(app, "run", return_value=CompletedProcess([], 0, stdout="log line\n", stderr="")) as mocked:
            app.job_logs("livestream-rec-tiktok-x-abc.service", tail=1000)
        args = mocked.call_args.args[0]
        self.assertIn("-n", args)
        self.assertEqual(args[args.index("-n") + 1], "1000")
        with self.assertRaises(ValueError):
            app.job_logs("evil.service")

    def test_restart_job_validates_unit(self):
        with patch.object(app, "run", return_value=CompletedProcess([], 0, stdout="", stderr="")) as mocked:
            app.restart_job("livestream-rec-tiktok-x-abc.service")
        self.assertEqual(mocked.call_args.args[0][0], "systemctl")
        self.assertIn("restart", mocked.call_args.args[0])
        with self.assertRaises(ValueError):
            app.restart_job("../../evil")

    def test_download_range(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "clip.mp4"
            video.write_bytes(b"0123456789")
            with patch.object(app, "RECORDINGS_DIR", directory):
                handler = _FakeHandler("/api/file?path=clip.mp4")
                handler.headers["Range"] = "bytes=2-5"
                handler.do_GET()
            raw = handler.wfile.getvalue()
            head, _, body = raw.partition(b"\r\n\r\n")
            lines = head.decode("latin-1").splitlines()
            self.assertEqual(lines[0].split()[1], "206")
            self.assertIn("Content-Range: bytes 2-5/10", lines)
            self.assertEqual(body, b"2345")

    def test_download_rejects_traversal(self):
        with patch.object(app, "RECORDINGS_DIR", "/tmp"):
            handler = _FakeHandler("/api/file?path=..%2F..%2Fetc%2Fpasswd")
            handler.do_GET()
        raw = handler.wfile.getvalue()
        head, _, _ = raw.partition(b"\r\n\r\n")
        self.assertEqual(head.decode("latin-1").splitlines()[0].split()[1], "404")

    def test_files_api_and_overview_platforms(self):

        jobs = [{"platform": "tiktok", "state": "active"}, {"platform": "tiktok", "state": "failed"}]
        with (
            patch.object(app, "list_jobs", return_value=jobs),
            patch.object(app, "list_files", return_value={"total": 0, "offset": 0, "files": []}),
            patch.object(app, "system_stats", return_value={"load": [0.1, 0.2, 0.3], "mem_total": 1000, "mem_available": 500}),
        ):
            data = app.overview()
        self.assertEqual(data["running"], 1)
        self.assertEqual(data["failed"], 1)
        self.assertEqual(data["platforms"], {"tiktok": 2})
        handler = _FakeHandler("/api/files")
        with patch.object(app, "list_files", return_value={"total": 0, "offset": 0, "files": []}):
            handler.do_GET()
        raw = handler.wfile.getvalue()
        head, _, body = raw.partition(b"\r\n\r\n")
        self.assertEqual(head.decode("latin-1").splitlines()[0].split()[1], "200")
        self.assertEqual(json.loads(body)["total"], 0)


    def test_start_job_forwards_quality(self):
        with patch.object(app, "list_jobs", return_value=[]), \
                patch.object(app, "run", return_value=CompletedProcess([], 0, stdout="", stderr="")) as mocked:
            app.start_job({"platform": "tiktok", "target": "@user", "quality": "720p"})
        argv = mocked.call_args.args[0]
        self.assertIn("--quality", argv)
        self.assertEqual(argv[argv.index("--quality") + 1], "720p")

    def test_start_job_defaults_to_best_quality(self):
        with patch.object(app, "list_jobs", return_value=[]), \
                patch.object(app, "run", return_value=CompletedProcess([], 0, stdout="", stderr="")) as mocked:
            app.start_job({"platform": "tiktok", "target": "@user"})
        argv = mocked.call_args.args[0]
        self.assertNotIn("--quality", argv)

    def test_start_job_rejects_invalid_quality(self):
        with patch.object(app, "list_jobs", return_value=[]), \
                patch.object(app, "run") as mocked:
            with self.assertRaises(ValueError):
                app.start_job({"platform": "tiktok", "target": "@user", "quality": "4k"})
        mocked.assert_not_called()

    def test_download_serves_inline_for_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "clip.mp4"
            video.write_bytes(b"0123456789")
            with patch.object(app, "RECORDINGS_DIR", directory):
                handler = _FakeHandler("/api/file?path=clip.mp4")
                handler.do_GET()
        head, _, _ = handler.wfile.getvalue().partition(b"\r\n\r\n")
        self.assertIn("Content-Disposition: inline", head.decode("latin-1"))

    def test_index_has_quality_selector_and_player(self):
        index = app.INDEX_FILE.read_text(encoding="utf-8")
        self.assertIn("1080p", index)
        self.assertIn("quality", index)
        self.assertIn("inline-player", index)
        self.assertIn("api/file", index)
        self.assertIn("播放", index)

    def test_index_retains_grid_and_flex_layout(self):
        # 布局原语必须保留（曾被合并后遗漏导致 UI 完全混乱）。
        index = app.INDEX_FILE.read_text(encoding="utf-8")
        for fragment in (
            ".stats{display:grid;grid-template-columns:repeat(4,1fr)",
            ".split{display:grid;grid-template-columns:1.3fr .7fr",
            "header{display:flex;justify-content:space-between",
            ".jobs{display:grid;gap:10px}",
            ".file-actions{display:flex",
            ".inline-player",
        ):
            self.assertIn(fragment, index, fragment)


class FrontendTemplateWiringTest(unittest.TestCase):
    """组件模板里的事件处理器必须在本组件 <script setup> 中定义。

    历史故障：任务列表（Tasks.vue）在拆分模块后漏了 taskActions 的 import，
    `@stop="askStop"` 等绑定解析为 undefined，点击"停止/重启/日志"毫无反应；
    这类断裂不会报构建错误，只有真机点击才暴露。
    """

    SRC = app.WEBUI_DIR / "frontend" / "src"
    IMPORT_NAMED = re.compile(r"import\s*\{([^}]*)\}\s*from")
    IMPORT_DEFAULT = re.compile(r"import\s+([A-Za-z_$][\w$]*)\s*(?:,|from)")
    DEFINITION = re.compile(r"(?:const|let|var|function|class)\s+([A-Za-z_$][\w$]*)")
    DESTRUCTURE = re.compile(r"(?:const|let|var)\s*\{([^}]*)\}")

    def _defined_names(self, script: str) -> set[str]:
        names = set(self.DEFINITION.findall(script))
        for block in self.IMPORT_NAMED.findall(script):
            names.update(part.split(" as ")[-1].strip() for part in block.split(",") if part.strip())
        names.update(self.IMPORT_DEFAULT.findall(script))
        for block in self.DESTRUCTURE.findall(script):
            names.update(part.split(":")[-1].strip() for part in block.split(",") if part.strip())
        return names

    def _handler_refs(self, template: str) -> set[str]:
        refs: set[str] = set()
        for expression in re.findall(r'@[\w.-]+="([^"]*)"', template):
            refs.update(re.findall(r"(?<![\w$])([A-Za-z_$][\w$]*)\s*(?=\()", expression))
            stripped = expression.strip()
            if re.fullmatch(r"[A-Za-z_$][\w$]*", stripped):
                refs.add(stripped)
        return {name for name in refs if not name.startswith("$")}

    def test_component_handlers_are_defined_in_script_setup(self):
        broken: list[str] = []
        for path in sorted(self.SRC.rglob("*.vue")):
            text = path.read_text(encoding="utf-8")
            template = re.search(r"<template>(.*?)</template>", text, re.S)
            script = re.search(r"<script setup>(.*?)</script>", text, re.S)
            if not (template and script):
                continue
            unknown = self._handler_refs(template.group(1)) - self._defined_names(script.group(1))
            if unknown:
                broken.append(f"{path.relative_to(self.SRC)}: {sorted(unknown)}")
        self.assertEqual(broken, [])


class TaskPauseResumeDeleteTest(unittest.TestCase):
    """暂停/继续/删除任务的后端语义。

    背景：单元由 `systemd-run --collect` 创建，停止后会被 systemd 回收（重新 start 会
    "Unit not found"）。暂停必须把启动参数留在任务目录（`state/tasks.json`），
    否则「继续」无法按原参数重新拉起。
    """

    UNIT = app.unit_name("tiktok", "chan")

    def setUp(self):
        base = Path(tempfile.mkdtemp(prefix="webui_state_test_"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        self.catalog_file = base / "tasks.json"
        for target, value in (("STATE_DIR", base), ("CATALOG_FILE", self.catalog_file)):
            patcher = patch.object(app, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _catalog(self) -> dict:
        return json.loads(self.catalog_file.read_text(encoding="utf-8"))

    def _spec(self) -> dict:
        return {"platform": "tiktok", "target": "chan", "quality": "720p", "cookie_file": "", "paused": False}

    def _unit_show(self, quality: str = "480p") -> CompletedProcess:
        """systemd show 的原始输出（ExecStart 用于从已存在单元反推启动参数）。"""
        return CompletedProcess([], 0, stdout=(
            f"Id={self.UNIT}\nDescription=Live recorder: tiktok chan\n"
            "ExecStart={ path=/usr/bin/bash ; argv[]=/usr/bin/bash /home/u/tk/record.sh chan "
            f"--quality {quality} ; ignore_errors=no ; start_time=[n/a] ; pid=1 ; code=(null) ; status=0/0 }}\n"
        ), stderr="")

    def test_pause_stops_unit_and_persists_spec(self):
        self.catalog_file.write_text(json.dumps({self.UNIT: self._spec()}), encoding="utf-8")
        with patch.object(app, "_live_units", return_value=[self.UNIT]), \
                patch.object(app, "run", return_value=CompletedProcess([], 0, stdout="", stderr="")) as mocked_run:
            app.pause_job(self.UNIT)
        self.assertEqual(mocked_run.call_args.args[0], [app.SYSTEMCTL, "stop", self.UNIT])
        # 暂停后单元已被回收：仍能从任务目录列出，且状态为 paused
        with patch.object(app, "_live_units", return_value=[]):
            jobs = app.list_jobs()
        self.assertEqual([(job["unit"], job["state"], job["live"]) for job in jobs], [(self.UNIT, "paused", "paused")])
        self.assertTrue(self._catalog()[self.UNIT]["paused"])

    def test_resume_respawns_unit_with_saved_arguments(self):
        paused = {**self._spec(), "paused": True}
        self.catalog_file.write_text(json.dumps({self.UNIT: paused}), encoding="utf-8")
        with patch.object(app, "_live_units", return_value=[]), \
                patch.object(app, "run", return_value=CompletedProcess([], 0, stdout="", stderr="")) as mocked_run:
            unit = app.resume_job(self.UNIT)
        self.assertEqual(unit, self.UNIT)
        argv = mocked_run.call_args.args[0]
        self.assertEqual(argv[0], app.SYSTEMD_RUN)
        self.assertIn(f"--unit={self.UNIT.removesuffix('.service')}", argv)
        # 画质等原始参数随「继续」一并恢复（完整命令尾部与新建时一致）
        self.assertEqual(argv[argv.index("--") + 1:], [
            "bash", str(app.PROJECT_ROOT / "tk/record.sh"), "chan", "--quality", "720p",
        ])
        self.assertFalse(self._catalog()[self.UNIT]["paused"])

    def test_pause_recovers_arguments_from_systemd_when_catalog_is_empty(self):
        """旧版本/命令行创建的任务没有目录记录，暂停时从单元 ExecStart 反推参数。"""
        with patch.object(app, "_live_units", return_value=[self.UNIT]), \
                patch.object(app, "run", side_effect=[
                    self._unit_show("480p"), CompletedProcess([], 0, stdout="", stderr="")
                ]):
            app.pause_job(self.UNIT)
        spec = self._catalog()[self.UNIT]
        self.assertEqual((spec["platform"], spec["target"], spec["quality"], spec["paused"]),
                         ("tiktok", "chan", "480p", True))

    def test_delete_stops_running_unit_and_drops_record(self):
        self.catalog_file.write_text(json.dumps({self.UNIT: self._spec()}), encoding="utf-8")
        with patch.object(app, "_live_units", return_value=[self.UNIT]), \
                patch.object(app, "run", return_value=CompletedProcess([], 0, stdout="", stderr="")) as mocked_run:
            app.delete_job(self.UNIT)
        self.assertEqual(mocked_run.call_args.args[0], [app.SYSTEMCTL, "stop", self.UNIT])
        self.assertEqual(self._catalog(), {})
        with patch.object(app, "_live_units", return_value=[]):
            self.assertEqual(app.list_jobs(), [])

    def test_deleting_paused_task_does_not_call_systemctl(self):
        self.catalog_file.write_text(json.dumps({self.UNIT: {**self._spec(), "paused": True}}), encoding="utf-8")
        with patch.object(app, "_live_units", return_value=[]), \
                patch.object(app, "run") as mocked_run:
            app.delete_job(self.UNIT)
        mocked_run.assert_not_called()
        self.assertEqual(self._catalog(), {})

    def test_pause_rejects_unit_that_is_not_running(self):
        with patch.object(app, "_live_units", return_value=[]), patch.object(app, "run") as mocked_run:
            with self.assertRaises(ValueError):
                app.pause_job(self.UNIT)
        mocked_run.assert_not_called()

    def test_resume_rejects_task_that_is_not_paused(self):
        self.catalog_file.write_text(json.dumps({self.UNIT: self._spec()}), encoding="utf-8")
        with patch.object(app, "_live_units", return_value=[self.UNIT]), patch.object(app, "run") as mocked_run:
            with self.assertRaises(ValueError):
                app.resume_job(self.UNIT)
        mocked_run.assert_not_called()

    def test_start_rejects_duplicate_of_paused_task(self):
        self.catalog_file.write_text(json.dumps({self.UNIT: {**self._spec(), "paused": True}}), encoding="utf-8")
        with patch.object(app, "_live_units", return_value=[]), patch.object(app, "run") as mocked_run:
            with self.assertRaises(ValueError) as ctx:
                app.start_job({"platform": "tiktok", "target": " CHAN ", "quality": "best"})
        self.assertIn("暂停", str(ctx.exception))
        mocked_run.assert_not_called()

    def test_restore_respawns_missing_nonpaused_task(self):
        self.catalog_file.write_text(json.dumps({self.UNIT: self._spec()}), encoding="utf-8")
        with patch.object(app, "_live_units", return_value=[]), \
                patch.object(app, "run", return_value=CompletedProcess([], 0, stdout="", stderr="")) as mocked_run:
            restored, failed = app.restore_jobs()
        self.assertEqual(restored, [self.UNIT])
        self.assertEqual(failed, {})
        argv = mocked_run.call_args.args[0]
        self.assertEqual(argv[0], app.SYSTEMD_RUN)
        self.assertIn(f"--unit={self.UNIT.removesuffix('.service')}", argv)
        self.assertEqual(self._catalog()[self.UNIT]["target"], "chan")

    def test_restore_skips_running_and_paused_tasks(self):
        paused_unit = app.unit_name("tiktok", "paused")
        catalog = {
            self.UNIT: self._spec(),
            paused_unit: {**self._spec(), "target": "paused", "paused": True},
        }
        self.catalog_file.write_text(json.dumps(catalog), encoding="utf-8")
        with patch.object(app, "_live_units", return_value=[self.UNIT]), \
                patch.object(app, "run") as mocked_run:
            restored, failed = app.restore_jobs()
        self.assertEqual((restored, failed), ([], {}))
        mocked_run.assert_not_called()

    def test_restore_failure_does_not_delete_catalog(self):
        self.catalog_file.write_text(json.dumps({self.UNIT: self._spec()}), encoding="utf-8")
        failure = CompletedProcess([], 1, stdout="", stderr="systemd unavailable")
        with patch.object(app, "_live_units", return_value=[]), patch.object(app, "run", return_value=failure):
            restored, failed = app.restore_jobs()
        self.assertEqual(restored, [])
        self.assertIn("systemd unavailable", failed[self.UNIT])
        self.assertIn(self.UNIT, self._catalog())

    def test_corrupt_catalog_does_not_break_listing(self):
        self.catalog_file.write_text("{ not json", encoding="utf-8")
        with patch.object(app, "_live_units", return_value=[]):
            self.assertEqual(app.list_jobs(), [])


class TaskControlHTTPTest(unittest.TestCase):
    """任务控制接口的路由（暂停/继续/删除任务，以及已移除的 /api/stop）。"""

    def test_delete_task_route_dispatches_to_delete_job(self):
        with patch.object(app, "delete_job") as mocked:
            status, _ = WebUIHTTPTest()._post("/api/delete-task", {"unit": "u.service"})
        self.assertEqual(status, HTTPStatus.OK)
        mocked.assert_called_once_with("u.service")

    def test_pause_and_resume_routes_dispatch(self):
        handler = WebUIHTTPTest()
        with patch.object(app, "pause_job") as paused:
            status, _ = handler._post("/api/pause", {"unit": "u.service"})
        self.assertEqual(status, HTTPStatus.OK)
        paused.assert_called_once_with("u.service")
        with patch.object(app, "resume_job", return_value="new.service") as resumed:
            status, body = handler._post("/api/resume", {"unit": "u.service"})
        self.assertEqual(status, HTTPStatus.OK)
        resumed.assert_called_once_with("u.service")
        self.assertEqual(json.loads(body), {"unit": "new.service"})

    def test_legacy_stop_route_is_gone(self):
        # 停止不再是独立操作：运行中的任务用「暂停」保留恢复能力，删除用 /api/delete-task。
        status, body = WebUIHTTPTest()._post("/api/stop", {"unit": "u.service"})
        self.assertEqual(status, HTTPStatus.NOT_FOUND)
        self.assertEqual(json.loads(body), {"error": "not found"})


if __name__ == "__main__":
    unittest.main()
