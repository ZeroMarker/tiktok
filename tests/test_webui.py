import io
import os
import tempfile
import unittest
from http import HTTPStatus
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from webui import app


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
        import json

        manifest = json.loads((app.WEBUI_DIR / "manifest.webmanifest").read_text())
        self.assertTrue(manifest["start_url"])
        purposes = {icon["purpose"] for icon in manifest["icons"]}
        self.assertIn("maskable", purposes)
        self.assertTrue(all((app.WEBUI_DIR / icon["src"]).is_file() for icon in manifest["icons"]))

    def test_api_requires_no_auth_token(self):
        import json

        # 认证已移除：无令牌请求必须被放行。
        status, content_type, body = self._get("/api/health")
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(json.loads(body)["ok"], True)

    def test_api_jobs_without_token_is_allowed(self):
        import json

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
                patch.object(app, "run") as mocked:
            with self.assertRaises(ValueError) as ctx:
                app.start_job({"platform": "tiktok", "target": " @some.user "})
        self.assertIn("已存在", str(ctx.exception))
        mocked.assert_not_called()

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
        import json

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
        self.assertIn("player-box", index)
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
            ".player-overlay{position:fixed",
        ):
            self.assertIn(fragment, index, fragment)


if __name__ == "__main__":
    unittest.main()
