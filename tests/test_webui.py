import os
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from webui import app


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

    def test_missing_auth_token_refuses_to_start(self):
        with patch.object(app, "AUTH_TOKEN", ""):
            with self.assertRaisesRegex(SystemExit, "LIVE_WEBUI_TOKEN"):
                app.main()

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
