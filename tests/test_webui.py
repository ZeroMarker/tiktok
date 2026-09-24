"""WebUI 单元测试。

控制面已是单进程模型（webui/recorder.py：任务 = 引擎线程，不再有 systemd
临时单元）；测试通过替换 recorder.build_engine 工厂为假引擎来驱动
暂停/继续/删除/重启/恢复语义，不触发真实网络与 ffmpeg。
"""

import io
import json
import os
import re
import shutil
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from webui import app
from webui import config as app_config
from webui import files as app_files
from webui import jobs as app_jobs
from webui import recorder as app_recorder
from webui import stats as app_stats

# 所有用例都在临时任务目录上运行：start_job 会持久化启动参数（state/tasks.json，
# 供「暂停/继续」使用），未隔离时会把测试数据写进真实部署目录。
_STATE_DIR = tempfile.TemporaryDirectory(prefix="webui_test_state_")
_STATE_PATCHES = [
    patch.object(app_config, "STATE_DIR", Path(_STATE_DIR.name)),
    patch.object(app_config, "CATALOG_FILE", Path(_STATE_DIR.name) / "tasks.json"),
]


def setUpModule() -> None:
    for patcher in _STATE_PATCHES:
        patcher.start()
    unittest.addModuleCleanup(_STATE_DIR.cleanup)


def tearDownModule() -> None:
    for patcher in _STATE_PATCHES:
        patcher.stop()


class _FakeEngine:
    """线程内假引擎：run() 阻塞到 request_stop；fail=True 模拟引擎构建/运行崩溃。"""

    def __init__(self, unit: str, spec: dict, fail: bool = False) -> None:
        self.unit = unit
        self.spec = dict(spec)
        self.fail = fail
        self.phase = "detecting"
        self.is_recording = False
        self._stop = threading.Event()

    def run(self):
        if self.fail:
            raise RuntimeError("boom")
        self._stop.wait(30)  # 模拟长时间检测/录制轮询
        return 0

    def request_stop(self) -> None:
        self.phase = "stopping"
        self._stop.set()


def _fake_build(fail: bool = False):
    def build(unit: str, spec: dict) -> _FakeEngine:
        return _FakeEngine(unit, spec, fail=fail)

    return build


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
        self.assertEqual(status, 200)
        self.assertIn("application/manifest+json", content_type)
        self.assertIn(b'"start_url"', body)

    def test_service_worker_served_as_javascript(self):
        status, content_type, _ = self._get("/sw.js")
        self.assertEqual(status, 200)
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
            self.assertEqual(status, 200, name)
            self.assertEqual(content_type, mime, name)
            self.assertEqual(body, (app.WEBUI_DIR / name).read_bytes(), name)

    def test_index_alias_served(self):
        status, content_type, _ = self._get("/index.html")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)

    def test_unknown_path_is_404(self):
        status, _, _ = self._get("/nope")
        self.assertEqual(status, 404)

    def test_manifest_icons_are_valid(self):
        manifest = json.loads((app.WEBUI_DIR / "manifest.webmanifest").read_text())
        self.assertTrue(manifest["start_url"])
        purposes = {icon["purpose"] for icon in manifest["icons"]}
        self.assertIn("maskable", purposes)
        self.assertTrue(all((app.WEBUI_DIR / icon["src"]).is_file() for icon in manifest["icons"]))

    def test_api_requires_no_auth_token(self):
        # 认证已移除：无令牌请求必须被放行。
        status, content_type, body = self._get("/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["ok"], True)

    def test_api_jobs_without_token_is_allowed(self):
        with patch.object(app_jobs, "list_jobs", return_value=[]):
            status, _, body = self._get("/api/jobs")
        self.assertEqual(status, 200)
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
    def setUp(self):
        # 每个用例一个全新的单进程调度器（假引擎），互不串扰。
        self.rec = app_recorder.Recorder(restart_backoff=0.05)
        patcher = patch.object(app_jobs, "_recorder", self.rec)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.rec.shutdown, 2)

    def test_unit_name_is_stable_and_safe(self):
        first = app.unit_name("tiktok", "@Some.User/live?a=1")
        self.assertEqual(first, app.unit_name("tiktok", "@Some.User/live?a=1"))
        self.assertRegex(first, r"^livestream-rec-tiktok-[a-z0-9-]+\.service$")

    def test_unit_name_distinguishes_targets(self):
        self.assertNotEqual(app.unit_name("kick", "one"), app.unit_name("kick", "two"))

    def test_start_job_rejects_duplicate_target(self):
        existing = [
            {"platform": "tiktok", "target": "@Some.User",
             "unit": "livestream-rec-tiktok-some-user-abc.service"}
        ]
        with patch.object(app_jobs, "list_jobs", return_value=existing), \
                patch.object(app_recorder, "build_engine", side_effect=AssertionError("不应启动引擎")):
            with self.assertRaises(ValueError) as ctx:
                app.start_job({"platform": "tiktok", "target": " @some.user "})
        self.assertIn("已存在", str(ctx.exception))
        # 重复任务不得真的启动任何线程
        self.assertEqual(self.rec.status(), [])

    def test_start_job_allows_different_case_on_other_platform(self):
        existing = [
            {"platform": "tiktok", "target": "@Some.User",
             "unit": "livestream-rec-tiktok-some-user-abc.service"}
        ]
        with patch.object(app_jobs, "list_jobs", return_value=existing), \
                patch.object(app_recorder, "build_engine", side_effect=_fake_build()):
            unit = app.start_job({"platform": "kick", "target": "@some.user"})
        self.assertTrue(unit.startswith("livestream-rec-kick-"))
        self.assertTrue(self.rec.is_running(unit))
        self.assertEqual(self.rec.get_spec(unit)["target"], "@some.user")

    def test_start_job_forwards_quality(self):
        with patch.object(app_jobs, "list_jobs", return_value=[]), \
                patch.object(app_recorder, "build_engine", side_effect=_fake_build()):
            unit = app.start_job({"platform": "tiktok", "target": "@user", "quality": "720p"})
        self.assertEqual(self.rec.get_spec(unit)["quality"], "720p")

    def test_start_job_defaults_to_best_quality(self):
        with patch.object(app_jobs, "list_jobs", return_value=[]), \
                patch.object(app_recorder, "build_engine", side_effect=_fake_build()):
            unit = app.start_job({"platform": "tiktok", "target": "@user"})
        self.assertEqual(self.rec.get_spec(unit)["quality"], "best")

    def test_start_job_rejects_invalid_quality(self):
        with patch.object(app_jobs, "list_jobs", return_value=[]), \
                patch.object(app_recorder, "build_engine", side_effect=AssertionError("不应启动")):
            with self.assertRaises(ValueError):
                app.start_job({"platform": "tiktok", "target": "@user", "quality": "4k"})
        self.assertEqual(self.rec.status(), [])

    def test_recent_files_uses_configured_recordings_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "channel"
            nested.mkdir()
            video = nested / "clip.mp4"
            video.write_bytes(b"video")
            (nested / "ignored.flv").write_bytes(b"stream")
            with patch.object(app_config, "RECORDINGS_DIR", directory):
                files = app.recent_files()
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["path"], os.path.join("channel", "clip.mp4"))

    def test_recent_files_handles_missing_directory(self):
        with patch.object(app_config, "RECORDINGS_DIR", "/definitely/missing/directory"):
            self.assertEqual(app.recent_files(), [])

    def test_overview_counts_live_and_waiting(self):
        jobs = [
            {"platform": "tiktok", "state": "active", "live": "live"},
            {"platform": "tiktok", "state": "active", "live": "waiting"},
            {"platform": "tiktok", "state": "failed", "live": "offline"},
        ]
        with (
            patch.object(app_jobs, "list_jobs", return_value=jobs),
            patch.object(app_files, "list_files", return_value={"total": 0, "offset": 0, "files": []}),
            patch.object(app_stats, "system_stats", return_value={"load": [0.1, 0.2, 0.3], "mem_total": 1000, "mem_available": 500}),
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
            with patch.object(app_config, "RECORDINGS_DIR", directory):
                data = app.list_files()
            self.assertEqual(data["total"], 3)
            self.assertEqual([f["name"] for f in data["files"]], ["clip_2.mp4", "live.mp4", "clip_1.mp4"])
            self.assertEqual(data["files"][0]["dir"], "tiktok_alpha")
            self.assertEqual(data["files"][1]["dir"], "soop_beta")
            with patch.object(app_config, "RECORDINGS_DIR", directory):
                filtered = app.list_files(query="clip_1")
            self.assertEqual(filtered["total"], 1)
            self.assertEqual(filtered["files"][0]["name"], "clip_1.mp4")

    def test_list_files_pagination(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i in range(5):
                (root / f"f{i}.mp4").write_bytes(b"x")
                os.utime(root / f"f{i}.mp4", (1_700_000_000 + i, 1_700_000_000 + i))
            with patch.object(app_config, "RECORDINGS_DIR", directory):
                page = app.list_files(limit=2, offset=2)
            self.assertEqual(page["total"], 5)
            self.assertEqual([f["name"] for f in page["files"]], ["f2.mp4", "f1.mp4"])

    def test_resolve_recording_rejects_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root.parent / "outside.mp4"
            outside.write_bytes(b"secret")
            with patch.object(app_config, "RECORDINGS_DIR", directory):
                self.assertIsNone(app.resolve_recording("../outside.mp4"))
                self.assertIsNone(app.resolve_recording("/etc/passwd"))
                self.assertIsNone(app.resolve_recording(""))
                self.assertIsNone(app.resolve_recording("missing.mp4"))
            (root / "ok.mp4").write_bytes(b"data")
            with patch.object(app_config, "RECORDINGS_DIR", directory):
                self.assertEqual(app.resolve_recording("ok.mp4").name, "ok.mp4")

    def test_delete_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "gone.mp4").write_bytes(b"data")
            with patch.object(app_config, "RECORDINGS_DIR", directory):
                app.delete_file("gone.mp4")
                self.assertFalse((root / "gone.mp4").exists())
                with self.assertRaises(ValueError):
                    app.delete_file("../etc/passwd")

    def test_job_logs_tails_engine_log_file(self):
        unit = app.unit_name("tiktok", "chan")
        with tempfile.TemporaryDirectory() as directory:
            path = app_recorder.engine_log_path(directory, "tiktok", unit)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(f"line{i}\n" for i in range(10)), encoding="utf-8")
            with patch.object(app_config, "RECORDINGS_DIR", directory), \
                    patch.object(app_jobs, "_recorder", _spec_recorder(unit, "tiktok")):
                tail = app.job_logs(unit, tail=4)
            self.assertEqual(tail.splitlines(), ["line6", "line7", "line8", "line9"])

    def test_job_logs_clamps_tail_and_handles_missing(self):
        unit = app.unit_name("tiktok", "chan")
        with tempfile.TemporaryDirectory() as directory:
            path = app_recorder.engine_log_path(directory, "tiktok", unit)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("".join(f"l{i}\n" for i in range(6000)), encoding="utf-8")
            with patch.object(app_config, "RECORDINGS_DIR", directory), \
                    patch.object(app_jobs, "_recorder", _spec_recorder(unit, "tiktok")):
                tail = app.job_logs(unit, tail=999999)  # 上限 5000 行
            self.assertEqual(len(tail.splitlines()), 5000)
            self.assertTrue(tail.endswith("l5999\n"))
        # 校验失败 / 无日志文件
        with self.assertRaises(ValueError):
            app.job_logs("evil.service")
        with patch.object(app_jobs, "_recorder", _spec_recorder(app.unit_name("kick", "x"), "kick")):
            self.assertEqual(app.job_logs(app.unit_name("kick", "x")), "")

    def test_restart_job_requires_running_task(self):
        unit = app.unit_name("tiktok", "chan")
        with self.assertRaises(ValueError):
            app.restart_job("../../evil")
        with self.assertRaises(RuntimeError):
            app.restart_job(unit)  # 未运行（含暂停中）

    def test_restart_job_respawns_thread(self):
        unit = app.unit_name("tiktok", "chan")
        with patch.object(app_recorder, "build_engine", side_effect=_fake_build()):
            self.rec.start(unit, {"platform": "tiktok", "target": "chan", "quality": "best"})
            app.restart_job(unit)
        self.assertTrue(self.rec.is_running(unit))
        status = self.rec.status()
        self.assertEqual(status[0]["unit"], unit)
        self.assertEqual(status[0]["restarts"], 0)  # 手动重启清零计数

    def test_download_range(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "clip.mp4"
            video.write_bytes(b"0123456789")
            with patch.object(app_config, "RECORDINGS_DIR", directory):
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
        with patch.object(app_config, "RECORDINGS_DIR", "/tmp"):
            handler = _FakeHandler("/api/file?path=..%2F..%2Fetc%2Fpasswd")
            handler.do_GET()
        raw = handler.wfile.getvalue()
        head, _, _ = raw.partition(b"\r\n\r\n")
        self.assertEqual(head.decode("latin-1").splitlines()[0].split()[1], "404")

    def test_files_api_and_overview_platforms(self):
        jobs = [{"platform": "tiktok", "state": "active"}, {"platform": "tiktok", "state": "failed"}]
        with (
            patch.object(app_jobs, "list_jobs", return_value=jobs),
            patch.object(app_files, "list_files", return_value={"total": 0, "offset": 0, "files": []}),
            patch.object(app_stats, "system_stats", return_value={"load": [0.1, 0.2, 0.3], "mem_total": 1000, "mem_available": 500}),
        ):
            data = app.overview()
        self.assertEqual(data["running"], 1)
        self.assertEqual(data["failed"], 1)
        self.assertEqual(data["platforms"], {"tiktok": 2})
        handler = _FakeHandler("/api/files")
        with patch.object(app_files, "list_files", return_value={"total": 0, "offset": 0, "files": []}):
            handler.do_GET()
        raw = handler.wfile.getvalue()
        head, _, body = raw.partition(b"\r\n\r\n")
        self.assertEqual(head.decode("latin-1").splitlines()[0].split()[1], "200")
        self.assertEqual(json.loads(body)["total"], 0)

    def test_download_serves_inline_for_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "clip.mp4"
            video.write_bytes(b"0123456789")
            with patch.object(app_config, "RECORDINGS_DIR", directory):
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


class RecorderStatusTest(unittest.TestCase):
    """单进程调度器状态聚合：字段形状与旧 systemctl show 聚合一致（前端零改动）。"""

    def setUp(self):
        self.rec = app_recorder.Recorder(restart_backoff=0.05)
        patcher = patch.object(app_jobs, "_recorder", self.rec)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.rec.shutdown, 2)

    def _start(self, platform="tiktok", target="chan"):
        unit = app.unit_name(platform, target)
        with patch.object(app_recorder, "build_engine", side_effect=_fake_build()):
            self.rec.start(unit, {"platform": platform, "target": target, "quality": "best"})
        return unit

    def test_status_shape_matches_frontend_contract(self):
        unit = self._start()
        # start 后引擎构建在线程内异步完成（activating 窗口），等它进入 running
        deadline = time.monotonic() + 2
        job = None
        while time.monotonic() < deadline:
            status = self.rec.status()
            if status:
                job = status[0]
                if job["substate"] == "running":
                    break
            time.sleep(0.01)
        self.assertIsNotNone(job)
        for key in ("unit", "state", "substate", "description", "started",
                    "platform", "target", "pid", "memory", "restarts", "live", "quality"):
            self.assertIn(key, job)
        self.assertEqual(job["unit"], unit)
        self.assertEqual(job["state"], "active")
        self.assertEqual(job["substate"], "running")
        self.assertEqual(job["live"], "waiting")  # 检测中（无 ffmpeg）
        self.assertEqual(job["description"], "Live recorder: tiktok chan")
        self.assertGreater(job["memory"], 0)
        self.assertGreater(job["pid"], 0)

    def test_recording_engine_reports_live(self):
        unit = self._start()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            engine = self.rec._tasks[unit].engine
            if engine is not None:
                engine.phase = "recording"
                engine.is_recording = True
                break
            time.sleep(0.01)
        job = next(j for j in self.rec.status() if j["unit"] == unit)
        self.assertEqual(job["live"], "live")
        self.assertEqual(job["substate"], "running")

    def test_construction_failure_reports_activating(self):
        unit = app.unit_name("tiktok", "broken")
        with patch.object(app_recorder, "build_engine", side_effect=ValueError("bad spec")):
            self.rec.start(unit, {"platform": "tiktok", "target": "broken", "quality": "best"})
            deadline = time.monotonic() + 2
            job = None
            while time.monotonic() < deadline:
                status = self.rec.status()
                if status:
                    job = status[0]
                    if job["substate"] == "activating":
                        break
                time.sleep(0.01)
        self.assertIsNotNone(job)
        self.assertEqual(job["state"], "active")
        self.assertEqual(job["substate"], "activating")

    def test_engine_crash_auto_restarts_with_backoff(self):
        """引擎异常退出按退避自动重启（等价旧 transient unit Restart=on-failure）。"""
        unit = app.unit_name("tiktok", "crashy")
        with patch.object(app_recorder, "build_engine", side_effect=_fake_build(fail=True)):
            self.rec.start(unit, {"platform": "tiktok", "target": "crashy", "quality": "best"})
            deadline = time.monotonic() + 3
            restarts = 0
            while time.monotonic() < deadline:
                status = self.rec.status()
                if status:
                    restarts = status[0]["restarts"]
                    if restarts >= 1:
                        break
                time.sleep(0.02)
        self.assertGreaterEqual(restarts, 1)

    def test_start_twice_raises_and_shutdown_stops_all(self):
        unit = self._start()
        with patch.object(app_recorder, "build_engine", side_effect=AssertionError("不应重建")):
            with self.assertRaises(RuntimeError):
                self.rec.start(unit, {"platform": "tiktok", "target": "chan"})
        engines_before = [t.engine for t in self.rec._tasks.values() if t.engine]
        self.rec.shutdown(timeout=2)
        self.assertEqual(self.rec.status(), [])
        for engine in engines_before:
            if engine is not None:
                self.assertTrue(engine._stop.is_set())

    def test_hidden_stopped_task_not_listed(self):
        """stop 置位中的任务对状态接口隐藏（暂停/删除瞬间不闪烁成运行中）。"""
        unit = self._start()
        task = self.rec._tasks[unit]
        task.stop.set()  # 模拟停止中窗口（线程仍在收尾）
        self.assertNotIn(unit, {j["unit"] for j in self.rec.status()})
        self.assertFalse(self.rec.is_running(unit))


def _spec_recorder(unit: str, platform: str) -> app_recorder.Recorder:
    """带一个"运行中"任务的调度器（仅用于 job_logs 反查平台，不启动线程）。"""
    rec = app_recorder.Recorder()
    task = app_recorder._Task(unit, {"platform": platform, "target": "x", "quality": "best"})
    task.thread = threading.Thread(target=lambda: None)
    task.thread.start()
    task.thread.join()
    rec._tasks[unit] = task
    return rec


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
    """暂停/继续/删除任务的单进程语义。

    任务目录（state/tasks.json）仍是期望状态：暂停 = 停线程 + paused 标记
    （参数留存）；继续 = 按参数重建线程；WebUI 启动时按目录恢复未暂停任务。
    """

    UNIT = app.unit_name("tiktok", "chan")

    def setUp(self):
        base = Path(tempfile.mkdtemp(prefix="webui_state_test_"))
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        self.catalog_file = base / "tasks.json"
        for target, value in (("STATE_DIR", base), ("CATALOG_FILE", self.catalog_file)):
            patcher = patch.object(app_config, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # 全新调度器 + 假引擎工厂（含构建工厂 patch 的清理顺序：先停线程再还原 patch）
        self.rec = app_recorder.Recorder(restart_backoff=0.05)
        rec_patcher = patch.object(app_jobs, "_recorder", self.rec)
        rec_patcher.start()
        self.addCleanup(rec_patcher.stop)
        build_patcher = patch.object(app_recorder, "build_engine", side_effect=_fake_build())
        build_patcher.start()
        self.addCleanup(build_patcher.stop)
        self.addCleanup(self.rec.shutdown, 2)

    def _catalog(self) -> dict:
        return json.loads(self.catalog_file.read_text(encoding="utf-8"))

    def _spec(self) -> dict:
        return {"platform": "tiktok", "target": "chan", "quality": "720p", "cookie_file": "", "paused": False}

    def test_pause_stops_thread_and_persists_spec(self):
        app.start_job({"platform": "tiktok", "target": "chan", "quality": "720p"})
        app.pause_job(self.UNIT)
        self.assertFalse(self.rec.is_running(self.UNIT))
        self.assertNotIn(self.UNIT, self.rec.running_units())
        # 暂停后线程已停：仍能从任务目录列出，且状态为 paused
        with patch.object(app_jobs, "_recorder", _empty_recorder()):
            jobs_list = app.list_jobs()
        self.assertEqual(
            [(job["unit"], job["state"], job["live"]) for job in jobs_list],
            [(self.UNIT, "paused", "paused")],
        )
        self.assertTrue(self._catalog()[self.UNIT]["paused"])
        self.assertEqual(self._catalog()[self.UNIT]["quality"], "720p")

    def test_resume_respawns_thread_with_saved_arguments(self):
        self.catalog_file.write_text(
            json.dumps({self.UNIT: {**self._spec(), "paused": True}}), encoding="utf-8"
        )
        unit = app.resume_job(self.UNIT)
        self.assertEqual(unit, self.UNIT)
        self.assertTrue(self.rec.is_running(unit))
        spec = self.rec.get_spec(unit)
        self.assertEqual(spec["quality"], "720p")  # 原始参数随「继续」一并恢复
        self.assertFalse(self._catalog()[self.UNIT]["paused"])

    def test_pause_recovers_arguments_from_runtime_when_catalog_is_empty(self):
        """任务目录缺失记录时（外部创建/旧数据），暂停从运行时反推参数。"""
        app.start_job({"platform": "tiktok", "target": "chan", "quality": "480p"})
        self.catalog_file.write_text("{}", encoding="utf-8")  # 目录被清空
        app.pause_job(self.UNIT)
        spec = self._catalog()[self.UNIT]
        self.assertEqual(
            (spec["platform"], spec["target"], spec["quality"], spec["paused"]),
            ("tiktok", "chan", "480p", True),
        )

    def test_delete_stops_running_thread_and_drops_record(self):
        app.start_job({"platform": "tiktok", "target": "chan"})
        app.delete_job(self.UNIT)
        self.assertFalse(self.rec.is_running(self.UNIT))
        self.assertEqual(self._catalog(), {})
        with patch.object(app_jobs, "_recorder", _empty_recorder()):
            self.assertEqual(app.list_jobs(), [])

    def test_deleting_paused_task_keeps_recordless_state(self):
        self.catalog_file.write_text(
            json.dumps({self.UNIT: {**self._spec(), "paused": True}}), encoding="utf-8"
        )
        app.delete_job(self.UNIT)
        self.assertEqual(self._catalog(), {})

    def test_pause_rejects_task_that_is_not_running(self):
        with self.assertRaises(ValueError):
            app.pause_job(self.UNIT)
        self.assertFalse(self.catalog_file.exists())

    def test_resume_rejects_task_that_is_not_paused(self):
        self.catalog_file.write_text(json.dumps({self.UNIT: self._spec()}), encoding="utf-8")
        with self.assertRaises(ValueError):
            app.resume_job(self.UNIT)
        self.assertFalse(self.rec.is_running(self.UNIT))

    def test_start_rejects_duplicate_of_paused_task(self):
        self.catalog_file.write_text(
            json.dumps({self.UNIT: {**self._spec(), "paused": True}}), encoding="utf-8"
        )
        with self.assertRaises(ValueError) as ctx:
            app.start_job({"platform": "tiktok", "target": " CHAN ", "quality": "best"})
        self.assertIn("暂停", str(ctx.exception))
        self.assertEqual(self.rec.status(), [])

    def test_restore_respawns_missing_nonpaused_task(self):
        self.catalog_file.write_text(json.dumps({self.UNIT: self._spec()}), encoding="utf-8")
        restored, failed = app.restore_jobs()
        self.assertEqual(restored, [self.UNIT])
        self.assertEqual(failed, {})
        self.assertTrue(self.rec.is_running(self.UNIT))
        self.assertEqual(self._catalog()[self.UNIT]["target"], "chan")

    def test_restore_skips_running_and_paused_tasks(self):
        paused_unit = app.unit_name("tiktok", "paused")
        catalog = {
            self.UNIT: self._spec(),
            paused_unit: {**self._spec(), "target": "paused", "paused": True},
        }
        self.catalog_file.write_text(json.dumps(catalog), encoding="utf-8")
        with patch.object(app_recorder, "build_engine", side_effect=AssertionError("不应启动")):
            self.rec.start(self.UNIT, self._spec())  # 已在运行
            restored, failed = app.restore_jobs()
        self.assertEqual((restored, failed), ([], {}))

    def test_restore_failure_does_not_delete_catalog(self):
        self.catalog_file.write_text(json.dumps({self.UNIT: self._spec()}), encoding="utf-8")
        with patch.object(self.rec, "start", side_effect=RuntimeError("启动失败: nope")):
            restored, failed = app.restore_jobs()
        self.assertEqual(restored, [])
        self.assertIn("nope", failed[self.UNIT])
        self.assertIn(self.UNIT, self._catalog())

    def test_restore_mismatched_unit_name_fails(self):
        # unit_name 由 (platform, target) 决定：目录里放一个名字对不上的记录必须失败且保留记录。
        other = app.unit_name("tiktok", "different")
        self.catalog_file.write_text(json.dumps({other: self._spec()}), encoding="utf-8")
        restored, failed = app.restore_jobs()
        self.assertEqual(restored, [])
        self.assertIn("不匹配", failed[other])
        self.assertIn(other, self._catalog())

    def test_corrupt_catalog_does_not_break_listing(self):
        self.catalog_file.write_text("{ not json", encoding="utf-8")
        self.assertEqual(app.list_jobs(), [])


def _empty_recorder() -> app_recorder.Recorder:
    return app_recorder.Recorder()


class TaskControlHTTPTest(unittest.TestCase):
    """任务控制接口的路由（暂停/继续/删除任务，以及已移除的 /api/stop）。"""

    def test_delete_task_route_dispatches_to_delete_job(self):
        with patch.object(app_jobs, "delete_job") as mocked:
            status, _ = WebUIHTTPTest()._post("/api/delete-task", {"unit": "u.service"})
        self.assertEqual(status, 200)
        mocked.assert_called_once_with("u.service")

    def test_pause_and_resume_routes_dispatch(self):
        handler = WebUIHTTPTest()
        with patch.object(app_jobs, "pause_job") as paused:
            status, _ = handler._post("/api/pause", {"unit": "u.service"})
            self.assertEqual(status, 200)
            paused.assert_called_once_with("u.service")
        with patch.object(app_jobs, "resume_job", return_value="new.service") as resumed:
            status, body = handler._post("/api/resume", {"unit": "u.service"})
        self.assertEqual(status, 200)
        resumed.assert_called_once_with("u.service")
        self.assertEqual(json.loads(body), {"unit": "new.service"})

    def test_legacy_stop_route_is_gone(self):
        # 停止不再是独立操作：运行中的任务用「暂停」保留恢复能力，删除用 /api/delete-task。
        status, body = WebUIHTTPTest()._post("/api/stop", {"unit": "u.service"})
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body), {"error": "not found"})


if __name__ == "__main__":
    unittest.main()
