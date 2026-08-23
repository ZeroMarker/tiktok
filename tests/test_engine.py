"""dlr 引擎与适配器单元测试。"""

import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from dlr.adapters import load_adapter  # noqa: E402
from dlr.adapters.base import extract_last_segment  # noqa: E402
from dlr.adapters.tiktok_extract import _find_nickname
from dlr.engine import Engine, sanitize_path_part  # noqa: E402

from unittest import mock  # noqa: E402
import dlr.adapters.tiktok as tiktok_mod  # noqa: E402
from dlr.adapters.tiktok import TikTokAdapter  # noqa: E402


class SanitizeTest(unittest.TestCase):
    def test_removes_path_specials(self):
        self.assertEqual(sanitize_path_part('a/b\\c:d*e?f"g<h>i|j'), "a_b_c_d_e_f_g_h_i_j")

    def test_strips_control_and_edges(self):
        self.assertEqual(sanitize_path_part("  ..hello..  "), "hello")

    def test_truncates_to_120(self):
        self.assertEqual(len(sanitize_path_part("x" * 500)), 120)

    def test_keeps_unicode_nickname(self):
        # 中文/日文/emoji 昵称应保留（路径与文件名均支持）
        self.assertEqual(sanitize_path_part("エミリ"), "エミリ")
        self.assertEqual(sanitize_path_part("张三 🎀"), "张三_🎀")
        # 控制字符仍被剔除，空白转下划线
        self.assertEqual(sanitize_path_part("a\x1fb"), "ab")
        self.assertEqual(sanitize_path_part(" a  b "), "a_b")


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
        self.assertEqual(engine.output_dir(None), Path("/tmp/rec/tiktok/emiri.okazaki"))
        # 昵称保留并拼进目录名
        self.assertEqual(engine.output_dir("エミリ"), Path("/tmp/rec/tiktok/emiri.okazaki_エミリ"))

    def test_output_dir_with_nickname(self):
        engine = Engine("soop", "player", "/tmp/rec", detect_interval=1, break_seconds=1)
        self.assertEqual(engine.output_dir("Nic Name"), Path("/tmp/rec/soop/player_Nic_Name"))

    def test_name_parts(self):
        engine = Engine("tiktok", "emiri.okazaki", "/tmp/rec", detect_interval=1, break_seconds=1)
        self.assertEqual(engine._name_parts(None), ["emiri.okazaki"])
        self.assertEqual(engine._name_parts("エミリ"), ["emiri.okazaki", "エミリ"])
        # 昵称与频道标识相同（或清洗后为空）时不重复拼接
        self.assertEqual(engine._name_parts("emiri.okazaki"), ["emiri.okazaki"])

    def test_record_prefix_includes_nickname(self):
        engine = Engine("soop", "player", "/tmp/rec", detect_interval=1, break_seconds=1)
        self.assertEqual("_".join(engine._name_parts(None)), "player")
        self.assertEqual("_".join(engine._name_parts("Nic Name")), "player_Nic_Name")

    def test_log_file_separated_by_platform(self):
        engine = Engine("tiktok", "emiri.okazaki", "/tmp/rec", detect_interval=1, break_seconds=1)
        self.assertEqual(
            engine.log_file(Path("/tmp/rec/logs"), "20260823"),
            Path("/tmp/rec/logs/tiktok/ffmpeg_record_emiri.okazaki_20260823.log"),
        )
        self.assertEqual(
            engine.log_file(Path("/tmp/rec/logs"), "20260823", "エミリ"),
            Path("/tmp/rec/logs/tiktok/ffmpeg_record_emiri.okazaki_エミリ_20260823.log"),
        )

    def test_refresh_nickname_updates_dir_once(self):
        engine = Engine("soop", "player", "/tmp/rec", detect_interval=1, break_seconds=1)
        engine.nickname = None
        engine.out_dir = engine.output_dir(None)
        engine.adapter.get_nickname = lambda: "Nice"
        engine._refresh_nickname()
        self.assertEqual(engine.nickname, "Nice")
        self.assertEqual(engine.out_dir, Path("/tmp/rec/soop/player_Nice"))
        # 已拿到昵称后不再重取，也不覆盖
        engine.adapter.get_nickname = lambda: "Other"
        engine._refresh_nickname()
        self.assertEqual(engine.nickname, "Nice")
        self.assertEqual(engine.out_dir, Path("/tmp/rec/soop/player_Nice"))

    def test_refresh_nickname_noop_when_still_missing(self):
        engine = Engine("soop", "player", "/tmp/rec", detect_interval=1, break_seconds=1)
        engine.nickname = None
        engine.out_dir = engine.output_dir(None)
        engine.adapter.get_nickname = lambda: None
        engine._refresh_nickname()
        self.assertIsNone(engine.nickname)
        self.assertEqual(engine.out_dir, engine.output_dir(None))


class DirWatchTest(unittest.TestCase):
    """输出目录被外部删除时的健壮性：守护线程自动重建，保证分段录制不中断。"""

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="dlr_engine_test_"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)

    def _engine(self, watch: int = 1):
        return Engine(
            "tiktok",
            "watch.ch",
            str(self.base / "rec"),
            detect_interval=1,
            break_seconds=1,
            dir_watch_interval=watch,
        )

    def _start_watcher(self, path: Path):
        engine = self._engine()
        stop = threading.Event()
        t = threading.Thread(target=engine._watch_dir, args=(path, stop), daemon=True)
        t.start()
        return engine, stop, t

    def test_ensure_dir_recreates_deleted_dir(self):
        engine = self._engine()
        out = engine.output_dir(None)
        out.mkdir(parents=True)
        shutil.rmtree(out)  # 模拟外部清理删除目录
        self.assertFalse(out.exists())
        engine._ensure_dir(out)
        self.assertTrue(out.is_dir())

    def test_watch_recreates_deleted_dir(self):
        out = self._engine().output_dir(None)
        out.mkdir(parents=True)
        engine, stop, t = self._start_watcher(out)
        try:
            shutil.rmtree(out)
            self.assertFalse(out.exists())
            time.sleep(2.5)  # 等一个监控周期（1s）后重建
            self.assertTrue(out.is_dir())
        finally:
            stop.set()
            t.join(timeout=3)

    def test_watch_recreates_parents_too(self):
        """父目录也一并被删（如清理整块 recordings/）时，能重建整条路径。"""
        out = self._engine().output_dir("エミリ")
        out.mkdir(parents=True)
        engine, stop, t = self._start_watcher(out)
        try:
            shutil.rmtree(out.parent)  # 删除整个 recordings/ 根
            time.sleep(2.5)
            self.assertTrue(out.is_dir())
        finally:
            stop.set()
            t.join(timeout=3)

    def test_watch_stops_cleanly(self):
        out = self._engine().output_dir(None)
        out.mkdir(parents=True)
        engine, stop, t = self._start_watcher(out)
        stop.set()
        t.join(timeout=3)
        self.assertFalse(t.is_alive())


class TikTokNicknameSourceTest(unittest.TestCase):
    """昵称获取的来源优先级：curl_cffi 优先，yt-dlp 只用 channel 显示名。"""

    def test_prefers_extract_over_ytdlp(self):
        a = TikTokAdapter("act.jp_official")
        with mock.patch.object(tiktok_mod, "extract_nickname", return_value="ACT女子"):
            self.assertEqual(a.get_nickname(), "ACT女子")

    def test_falls_back_to_channel_not_uploader(self):
        a = TikTokAdapter("emiri.okazaki")
        channels = []
        def fake_run(cmd):
            channels.append(cmd)
            # 只响应 channel 字段（显示名）；不应请求 uploader
            return "丘咲エミリ 本人" if "%(channel)s" in cmd else None
        with mock.patch.object(tiktok_mod, "extract_nickname", return_value=None):
            a.run_capture = fake_run
            self.assertEqual(a.get_nickname(), "丘咲エミリ 本人")
        printed = [" ".join(str(x) for x in c) for c in channels]
        self.assertTrue(any("channel" in p for p in printed))
        self.assertFalse(any("uploader" in p for p in printed))

    def test_genuine_nickname_equal_slug_accepted(self):
        """真实显示名恰好等于 handle（如 emma_kusunoki）也应被接受并返回。"""
        a = TikTokAdapter("emma_kusunoki")
        with mock.patch.object(tiktok_mod, "extract_nickname", return_value="emma_kusunoki"):
            self.assertEqual(a.get_nickname(), "emma_kusunoki")

    def test_nickname_equal_slug_dir_deduplicates(self):
        """昵称=slug（如 emma_kusunoki）时输出目录不重复拼后缀。"""
        engine = Engine("tiktok", "emma_kusunoki", "/tmp/rec", detect_interval=1, break_seconds=1)
        self.assertEqual(engine.output_dir("emma_kusunoki"), Path("/tmp/rec/tiktok/emma_kusunoki"))


class NicknameGuardTest(unittest.TestCase):
    """引擎侧昵称接受逻辑：昵称等于 handle 不阻塞补获取，也不过度拒绝。"""

    def test_find_nickname_nested(self):
        scope = {"webapp.user-detail": {"userInfo": {"user": {"nickname": "丘咲エミリ 本人"}}}}
        self.assertEqual(_find_nickname(scope), "丘咲エミリ 本人")
        self.assertIsNone(_find_nickname({"a": {}}))

    def test_refresh_accepts_nickname_equal_slug(self):
        """昵称=slug（如 emma_kusunoki）是合法昵称，应接受并终止补获取（不再每轮重试）。"""
        engine = Engine("tiktok", "emma_kusunoki", "/tmp/rec", detect_interval=1, break_seconds=1)
        engine.nickname = None
        engine.out_dir = engine.output_dir(None)
        engine.adapter.get_nickname = lambda: "emma_kusunoki"
        engine._refresh_nickname()
        self.assertEqual(engine.nickname, "emma_kusunoki")
        # 已拿到昵称后不再重取
        engine.adapter.get_nickname = lambda: None
        engine._refresh_nickname()
        self.assertEqual(engine.nickname, "emma_kusunoki")

    def test_refresh_accepts_real_nickname(self):
        engine = Engine("tiktok", "act.jp_official", "/tmp/rec", detect_interval=1, break_seconds=1)
        engine.nickname = None
        engine.out_dir = engine.output_dir(None)
        engine.adapter.get_nickname = lambda: "ACT女子"
        engine._refresh_nickname()
        self.assertEqual(engine.nickname, "ACT女子")


if __name__ == "__main__":
    unittest.main()
