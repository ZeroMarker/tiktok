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


class WebUIHelpersTest(unittest.TestCase):
    def test_unit_name_is_stable_and_safe(self):
        first = app.unit_name("tiktok", "@Some.User/live?a=1")
        self.assertEqual(first, app.unit_name("tiktok", "@Some.User/live?a=1"))
        self.assertRegex(first, r"^livestream-rec-tiktok-[a-z0-9-]+\.service$")

    def test_unit_name_distinguishes_targets(self):
        self.assertNotEqual(app.unit_name("kick", "one"), app.unit_name("kick", "two"))

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


if __name__ == "__main__":
    unittest.main()
