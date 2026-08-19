"""dlr 引擎与适配器单元测试。"""

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from dlr.adapters import load_adapter  # noqa: E402
from dlr.adapters.base import extract_last_segment  # noqa: E402
from dlr.engine import Engine, sanitize_path_part  # noqa: E402


class SanitizeTest(unittest.TestCase):
    def test_removes_path_specials(self):
        self.assertEqual(sanitize_path_part('a/b\\c:d*e?f"g<h>i|j'), "a_b_c_d_e_f_g_h_i_j")

    def test_strips_control_and_edges(self):
        self.assertEqual(sanitize_path_part("  ..hello..  "), "hello")

    def test_truncates_to_120(self):
        self.assertEqual(len(sanitize_path_part("x" * 500)), 120)


class ExtractSegmentTest(unittest.TestCase):
    def test_url_variants(self):
        self.assertEqual(extract_last_segment("https://www.tiktok.com/@emiri.okazaki/live"), "emiri.okazaki")
        self.assertEqual(extract_last_segment("https://kick.com/someuser?tab=live"), "someuser")
        self.assertEqual(extract_last_segment("https://chzzk.naver.com/live/abc123/"), "abc123")
        self.assertEqual(extract_last_segment("@kobiritukii"), "kobiritukii")
        self.assertEqual(extract_last_segment("plainname"), "plainname")


class AdapterDispatchTest(unittest.TestCase):
    def test_ytdlp_platforms(self):
        for platform in ("youtube", "kick", "chzzk", "soop"):
            adapter = load_adapter(platform, "some_channel")
            self.assertEqual(adapter.platform, platform)
            self.assertEqual(adapter.identifier, "some_channel")

    def test_tiktok(self):
        adapter = load_adapter("tiktok", "https://www.tiktok.com/@emiri.okazaki/live")
        self.assertEqual(adapter.identifier, "emiri.okazaki")
        self.assertTrue(adapter.bsf_aac)

    def test_douyin(self):
        adapter = load_adapter("douyin", "1930162853")
        self.assertEqual(adapter.identifier, "1930162853")

    def test_unknown_platform_raises(self):
        with self.assertRaises(ValueError):
            load_adapter("unknown", "x")


class LiveURLTest(unittest.TestCase):
    def test_youtube_builds_live_url(self):
        adapter = load_adapter("youtube", "SomeHandle")
        self.assertEqual(adapter.live_url, "https://www.youtube.com/@SomeHandle/live")
        adapter = load_adapter("youtube", "https://youtube.com/@x/live")
        self.assertEqual(adapter.live_url, "https://youtube.com/@x/live")

    def test_soop_builds_live_url(self):
        adapter = load_adapter("soop", "playerid")
        self.assertEqual(adapter.live_url, "https://play.sooplive.co.kr/playerid")

    def test_kick_and_chzzk(self):
        self.assertEqual(load_adapter("kick", "user").live_url, "https://kick.com/user")
        self.assertEqual(load_adapter("chzzk", "abc").live_url, "https://chzzk.naver.com/live/abc")


class OutputDirTest(unittest.TestCase):
    def test_output_dir_layout(self):
        engine = Engine("tiktok", "emiri.okazaki", "/tmp/rec", detect_interval=1, break_seconds=1)
        self.assertEqual(engine.output_dir(None), Path("/tmp/rec/tiktok_emiri.okazaki"))
        self.assertEqual(engine.output_dir("エミリ"), Path("/tmp/rec/tiktok_emiri.okazaki"))

    def test_output_dir_with_nickname(self):
        engine = Engine("soop", "player", "/tmp/rec", detect_interval=1, break_seconds=1)
        self.assertEqual(engine.output_dir("Nic Name"), Path("/tmp/rec/soop_player_Nic_Name"))


if __name__ == "__main__":
    unittest.main()
