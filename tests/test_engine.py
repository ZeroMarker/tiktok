"""dlr 引擎与适配器单元测试。"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from dlr.adapters import load_adapter  # noqa: E402
from dlr.adapters.base import extract_last_segment  # noqa: E402
from dlr.adapters.base import normalize_quality, pick_flv_url, quality_height  # noqa: E402
import dlr.adapters.tiktok_extract as tiktok_extract_mod  # noqa: E402
from dlr.adapters.tiktok_extract import _find_nickname, _find_nickname_from_sigi
from dlr.adapters.tiktok_extract import _stream_url_from_sigi
import dlr.engine as engine_mod  # noqa: E402
from dlr.engine import Engine, sanitize_path_part  # noqa: E402
import dlr.browserd as browserd_mod  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

from unittest import mock  # noqa: E402
import dlr.adapters.tiktok as tiktok_mod  # noqa: E402
from dlr.adapters.tiktok import TikTokAdapter  # noqa: E402


class TikTokRenderedStreamTest(unittest.TestCase):
    def test_extracts_video_flv_from_serialized_stream_data(self):
        sigi = {"LiveRoom": {"liveRoomUserInfo": {"liveRoom": {
            "streamData": {"pull_data": {"stream_data": __import__("json").dumps({
                "data": {"hd": {"main": {
                    "flv": "https://cdn.example/video.flv",
                    "hls": "https://cdn.example/video.m3u8",
                }}, "ao": {"main": {
                    "flv": "https://cdn.example/audio.flv?only_audio=1",
                }}}
            })}}
        }}}}
        html = '<script id="SIGI_STATE">' + __import__("json").dumps(sigi) + "</script>"
        self.assertEqual(_stream_url_from_sigi(html), "https://cdn.example/video.flv")





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

    def test_refresh_nickname_sets_nickname_once(self):
        engine = Engine("soop", "player", "/tmp/rec", detect_interval=1, break_seconds=1)
        engine.nickname = None
        engine.adapter.get_nickname = lambda: "Nice"
        engine._refresh_nickname()
        self.assertEqual(engine.nickname, "Nice")
        # 已拿到昵称后不再重取，也不覆盖
        engine.adapter.get_nickname = lambda: "Other"
        engine._refresh_nickname()
        self.assertEqual(engine.nickname, "Nice")

    def test_refresh_nickname_noop_when_still_missing(self):
        engine = Engine(
            "soop",
            "player",
            "/tmp/rec",
            detect_interval=1,
            break_seconds=1,
            nickname_attempts=2,
            nickname_retry_delay=0,
        )
        engine.nickname = None
        engine.out_dir = engine.output_dir(None)
        calls = {"n": 0}

        def fake_nickname():
            calls["n"] += 1
            return None

        engine.adapter.get_nickname = fake_nickname
        engine._refresh_nickname()
        self.assertIsNone(engine.nickname)
        self.assertEqual(engine.out_dir, engine.output_dir(None))
        # 失败时按 nickname_attempts 重试，而不是一次就放弃
        self.assertEqual(calls["n"], 2)

    def test_refresh_nickname_retries_then_succeeds(self):
        """偶发失败（网络抖动）应在重试后拿到昵称，避免退化成纯 slug 目录。"""
        engine = Engine(
            "soop",
            "player",
            "/tmp/rec",
            detect_interval=1,
            break_seconds=1,
            nickname_attempts=3,
            nickname_retry_delay=0,
        )
        engine.nickname = None
        calls = {"n": 0}

        def fake_nickname():
            calls["n"] += 1
            return None if calls["n"] < 3 else "Nic Name"

        engine.adapter.get_nickname = fake_nickname
        engine._refresh_nickname()
        self.assertEqual(engine.nickname, "Nic Name")
        self.assertEqual(calls["n"], 3)


class OutputDirCreationTest(unittest.TestCase):
    """开播确认后才创建输出目录：杜绝"无昵称空目录 + 昵称目录"双目录残留。"""

    def test_no_stale_nickname_dir_when_nickname_appears_late(self):
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        root = Path(base) / "rec"
        engine = Engine("tiktok", "emiri", str(root), detect_interval=1, break_seconds=1)
        engine.nickname = None
        engine.out_dir = None

        nickname_calls = {"n": 0}

        def fake_nickname():
            nickname_calls["n"] += 1
            return "エミリ"

        engine.adapter.get_nickname = fake_nickname

        detect_calls = {"n": 0}

        def fake_detect():
            detect_calls["n"] += 1
            # 第一轮未开播，第二轮抓到源
            return None if detect_calls["n"] == 1 else "http://stream"

        engine.adapter.detect_stream_url = fake_detect

        def fake_record(out_dir, log_dir, stream_url, nickname):
            engine.out_dir = out_dir
            engine.nickname = nickname
            engine._stopping = True

        engine._record = fake_record
        engine.run()

        # 只在开播确认后用昵称目录；无昵称前缀目录从未被创建
        self.assertEqual(engine.nickname, "エミリ")
        self.assertEqual(nickname_calls["n"], 1)
        self.assertEqual(engine.out_dir, engine.output_dir("エミリ"))
        self.assertTrue(engine.output_dir("エミリ").is_dir())
        self.assertFalse(engine.output_dir(None).exists())

    def test_dir_name_locked_after_first_round(self):
        """首回合昵称失败退化成 slug 目录后，后续回合取到昵称也不换目录名。

        换名会让同一场录制的分段分裂到 <slug> 和 <slug>_<昵称> 两个目录。
        """
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        root = Path(base) / "rec"
        engine = Engine(
            "tiktok",
            "emiri",
            str(root),
            detect_interval=1,
            break_seconds=1,
            nickname_attempts=1,
            nickname_retry_delay=0,
        )
        engine.nickname = None
        engine.out_dir = None

        calls = {"n": 0}

        def fake_nickname():
            calls["n"] += 1
            return None if calls["n"] == 1 else "エミリ"

        engine.adapter.get_nickname = fake_nickname
        engine.adapter.detect_stream_url = lambda: "http://stream"

        records = []

        def fake_record(out_dir, log_dir, stream_url, nickname):
            records.append((out_dir, nickname))
            if len(records) == 2:
                engine._stopping = True

        engine._record = fake_record
        engine.run()

        # 两回合都用首回合定下的纯 slug 目录，第二回合不再补取昵称
        self.assertEqual(len(records), 2)
        self.assertEqual(calls["n"], 1)
        self.assertEqual(records[0][0], engine.output_dir(None))
        self.assertEqual(records[1][0], engine.output_dir(None))
        self.assertTrue(engine.output_dir(None).is_dir())
        self.assertFalse(engine.output_dir("エミリ").exists())

    def test_restart_regains_nickname_across_offline_rounds(self):
        """重启后内存昵称清零：开播前的每轮轮询都应补抓昵称。

        首个窗口抓取失败（如 WAF 限流）、下一轮成功时，开播首轮仍能用
        昵称目录，不退化成纯 slug 目录（否则与既有昵称目录分裂并存）。
        """
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        root = Path(base) / "rec"
        engine = Engine(
            "tiktok",
            "emiri",
            str(root),
            detect_interval=1,
            break_seconds=1,
            nickname_attempts=1,
            nickname_retry_delay=0,
        )

        calls = {"n": 0}

        def fake_nickname():
            calls["n"] += 1
            return None if calls["n"] == 1 else "エミリ"

        engine.adapter.get_nickname = fake_nickname

        detect_calls = {"n": 0}

        def fake_detect():
            detect_calls["n"] += 1
            return None if detect_calls["n"] == 1 else "http://stream"

        engine.adapter.detect_stream_url = fake_detect

        records = []

        def fake_record(out_dir, log_dir, stream_url, nickname):
            records.append(out_dir)
            engine._stopping = True

        engine._record = fake_record
        engine.run()

        # 第 1 轮（未开播）补抓失败，第 2 轮开播前补抓成功 → 用昵称目录
        self.assertEqual(engine.nickname, "エミリ")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0], engine.output_dir("エミリ"))
        self.assertTrue(engine.output_dir("エミリ").is_dir())
        self.assertFalse(engine.output_dir(None).exists())

    def test_falls_back_to_slug_dir_when_nickname_always_fails(self):
        """昵称重试全部失败时仍要录制：目录退化为纯频道标识。"""
        base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        root = Path(base) / "rec"
        engine = Engine(
            "tiktok",
            "emiri",
            str(root),
            detect_interval=1,
            break_seconds=1,
            nickname_attempts=2,
            nickname_retry_delay=0,
        )
        engine.nickname = None
        engine.out_dir = None
        engine.adapter.get_nickname = lambda: None
        engine.adapter.detect_stream_url = lambda: "http://stream"

        def fake_record(out_dir, log_dir, stream_url, nickname):
            engine.out_dir = out_dir
            engine._stopping = True

        engine._record = fake_record
        engine.run()

        self.assertIsNone(engine.nickname)
        self.assertEqual(engine.out_dir, engine.output_dir(None))
        self.assertTrue(engine.output_dir(None).is_dir())


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


class TikTokDetectionStrategyTest(unittest.TestCase):
    def test_browser_fallback_runs_only_every_third_miss(self):
        adapter = TikTokAdapter("example")
        adapter.run_capture = mock.Mock(return_value=None)
        with mock.patch.object(tiktok_mod, "get_stream_url", return_value=None) as get_url:
            for _ in range(3):
                self.assertIsNone(adapter.detect_stream_url())

        self.assertEqual(
            [call.kwargs["allow_browser"] for call in get_url.call_args_list],
            [False, False, True],
        )
        self.assertTrue(all(call.kwargs["try_ytdlp"] is False for call in get_url.call_args_list))
        # 轻量检测（含 Cookie 透传）每轮都跑；yt-dlp 只在升级轮冷启动一次
        self.assertEqual(len(get_url.call_args_list), 3)
        self.assertTrue(all("cookies" in call.kwargs for call in get_url.call_args_list))
        self.assertEqual(adapter.run_capture.call_count, 1)

    def test_success_resets_browser_fallback_counter(self):
        adapter = TikTokAdapter("example")
        adapter._lightweight_misses = 2  # 下一轮即升级轮
        adapter.run_capture = mock.Mock(return_value="https://cdn.example/live.flv")
        with mock.patch.object(tiktok_mod, "get_stream_url", return_value=None) as get_url:
            self.assertEqual(
                adapter.detect_stream_url(), "https://cdn.example/live.flv"
            )
        self.assertEqual(adapter._lightweight_misses, 0)
        # 顺序契约：轻量检测每轮先行，yt-dlp 仅在升级轮兜底
        get_url.assert_called_once()


class BrowserdClientTest(unittest.TestCase):
    """共享渲染客户端：服务不可用必须降级为 None，绝不抛异常打断检测轮询。"""

    class _Stub(BaseHTTPRequestHandler):
        captured: dict = {}

        def log_message(self, *_args) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            type(self).captured = json.loads(self.rfile.read(length))
            body = b"<html><body>dom</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def _serve(self) -> ThreadingHTTPServer:
        server = ThreadingHTTPServer(("127.0.0.1", 0), self._Stub)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return server

    def test_render_document_passes_url_and_wait_js(self):
        server = self._serve()
        url = f"http://127.0.0.1:{server.server_address[1]}"
        with mock.patch.dict(os.environ, {"TIKTOK_BROWSERD_URL": url}):
            html = browserd_mod.render_document(
                "https://www.tiktok.com/@x/live", timeout=5, wait_js="ready?"
            )
        self.assertEqual(html, "<html><body>dom</body></html>")
        self.assertEqual(self._Stub.captured["url"], "https://www.tiktok.com/@x/live")
        self.assertEqual(self._Stub.captured["wait_js"], "ready?")
        self.assertEqual(self._Stub.captured["timeout"], 5)

    def test_render_document_returns_none_when_service_down(self):
        # 端口 1 无监听：连接被拒绝必须变成 None，而不是异常冒泡
        with mock.patch.dict(
            os.environ, {"TIKTOK_BROWSERD_URL": "http://127.0.0.1:1"}
        ):
            self.assertIsNone(
                browserd_mod.render_document("https://example/live", timeout=2)
            )

    def test_browser_probe_extracts_flv_from_rendered_dom(self):
        stream_data = json.dumps(
            {"data": {"hd": {"main": {"flv": "https://cdn.example/live.flv"}}}}
        )
        sigi = {
            "LiveRoom": {
                "liveRoomUserInfo": {
                    "liveRoom": {"streamData": {"pull_data": {"stream_data": stream_data}}}
                }
            }
        }
        html = '<script id="SIGI_STATE">' + json.dumps(sigi) + "</script>"
        with mock.patch.object(browserd_mod, "render_document", return_value=html) as render:
            self.assertEqual(
                tiktok_extract_mod._get_stream_url_with_browser("someone"),
                "https://cdn.example/live.flv",
            )
        # 等待条件必须锚定 streamData（水合完成），而不是页面加载即返回
        self.assertIn("streamData", render.call_args.kwargs["wait_js"])

    def test_browser_probe_returns_none_when_render_fails(self):
        with mock.patch.object(browserd_mod, "render_document", return_value=None):
            self.assertIsNone(
                tiktok_extract_mod._get_stream_url_with_browser("someone")
            )


class BrowserdRenderPageTest(unittest.TestCase):
    """共享渲染服务端：按 wait_js 等待取 DOM，任何路径都关闭标签页。"""

    class _FakeChrome:
        def __init__(self, ready: list, html: str) -> None:
            self.ready = list(ready)
            self.html = html
            self.calls: list = []

        def ensure(self) -> None:
            self.calls.append(("ensure", None, None))

        def call(self, method, params=None, *, session_id=None, timeout=15):
            self.calls.append((method, params, session_id))
            if method == "Target.createTarget":
                return {"targetId": "T1"}
            if method == "Target.attachToTarget":
                return {"sessionId": "S1"}
            if method == "Runtime.evaluate":
                if params["expression"] == "document.documentElement.outerHTML":
                    return {"result": {"value": self.html}}
                value = self.ready.pop(0) if self.ready else False
                return {"result": {"value": value}}
            return {}

    def test_waits_for_js_then_returns_dom_and_closes_target(self):
        chrome = self._FakeChrome([False, True], "<html>ok</html>")
        html = browserd_mod.render_page(
            chrome, "https://example/live", timeout=5, wait_js="ready?"
        )
        self.assertEqual(html, "<html>ok</html>")
        methods = [call[0] for call in chrome.calls]
        self.assertIn("Page.navigate", methods)
        self.assertIn("Target.closeTarget", methods)
        navigate = next(c for c in chrome.calls if c[0] == "Page.navigate")
        self.assertEqual(navigate[1], {"url": "https://example/live"})
        self.assertEqual(navigate[2], "S1")  # 导航必须落在标签页会话上
        # 先关标签页再取 DOM 之外的顺序无所谓，但 closeTarget 必须在最后兜底执行
        self.assertEqual(methods[-1], "Target.closeTarget")

    def test_deadline_path_still_returns_dom_and_closes_target(self):
        chrome = self._FakeChrome([], "<html>challenge</html>")
        html = browserd_mod.render_page(
            chrome, "https://example/live", timeout=0, wait_js="never"
        )
        self.assertEqual(html, "<html>challenge</html>")
        methods = [call[0] for call in chrome.calls]
        self.assertIn("Runtime.evaluate", methods)  # 至少抓了一次 DOM
        self.assertEqual(methods[-1], "Target.closeTarget")
        close = next(c for c in chrome.calls if c[0] == "Target.closeTarget")
        self.assertEqual(close[1], {"targetId": "T1"})


class DetectDelayTest(unittest.TestCase):
    def test_jitter_range_is_120_to_300_seconds(self):
        engine = Engine(
            "tiktok",
            "example",
            "/tmp/rec",
            detect_interval=210,
            detect_jitter=90,
        )
        with mock.patch.object(engine_mod.random, "randint", return_value=177) as randint:
            self.assertEqual(engine._next_detect_delay(), 177)
        randint.assert_called_once_with(120, 300)

    def test_zero_jitter_keeps_fixed_interval(self):
        engine = Engine(
            "tiktok", "example", "/tmp/rec", detect_interval=30, detect_jitter=0
        )
        self.assertEqual(engine._next_detect_delay(), 30)


class NicknameGuardTest(unittest.TestCase):
    """引擎侧昵称接受逻辑：昵称等于 handle 不阻塞补获取，也不过度拒绝。"""

    def test_find_nickname_nested(self):
        scope = {"webapp.user-detail": {"userInfo": {"user": {"nickname": "丘咲エミリ 本人"}}}}
        self.assertEqual(_find_nickname(scope), "丘咲エミリ 本人")
        self.assertIsNone(_find_nickname({"a": {}}))

    def test_sigi_live_room_user(self):
        """直播页 SIGI_STATE：liveRoomUserInfo.user 是频道本人时取昵称。"""
        sigi = {
            "LiveRoom": {
                "liveRoomUserInfo": {
                    "user": {"uniqueId": "emiri.okazaki", "nickname": "丘咲エミリ 本人"},
                }
            }
        }
        self.assertEqual(_find_nickname_from_sigi(sigi, "emiri.okazaki"), "丘咲エミリ 本人")

    def test_sigi_user_module_match(self):
        """liveRoomUserInfo 缺失时，从 UserModule 按 uniqueId 匹配频道用户。"""
        sigi = {
            "UserModule": {
                "users": {
                    "1": {"uniqueId": "other.user", "nickname": "别人"},
                    "2": {"uniqueId": "emiri.okazaki", "nickname": "丘咲エミリ 本人"},
                }
            }
        }
        self.assertEqual(_find_nickname_from_sigi(sigi, "emiri.okazaki"), "丘咲エミリ 本人")

    def test_sigi_no_matching_user(self):
        """页面里没有该频道用户时返回 None，不误取他人昵称。"""
        sigi = {
            "UserModule": {"users": {"1": {"uniqueId": "other.user", "nickname": "别人"}}}
        }
        self.assertIsNone(_find_nickname_from_sigi(sigi, "emiri.okazaki"))
        self.assertIsNone(_find_nickname_from_sigi({}, "emiri.okazaki"))

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


class QualitySelectTest(unittest.TestCase):
    def test_quality_height_map(self):
        self.assertIsNone(quality_height("best"))
        self.assertEqual(quality_height("1080p"), 1080)
        self.assertEqual(quality_height("720p"), 720)
        self.assertEqual(quality_height("480p"), 480)
        with self.assertRaises(ValueError):
            quality_height("4k")

    def test_pick_flv_url(self):
        flv = {"ORIGIN": "o", "FULL_HD1": "f", "HD1": "h", "SD1": "s", "SD2": "s2"}
        self.assertEqual(pick_flv_url(flv, None), "o")
        self.assertEqual(pick_flv_url(flv, 1080), "o")
        self.assertEqual(pick_flv_url(flv, 720), "h")
        self.assertEqual(pick_flv_url(flv, 480), "s")
        # 全部超出上限 → 退回最低可用
        self.assertEqual(pick_flv_url({"HD1": "h"}, 360), "h")
        self.assertIsNone(pick_flv_url({}, 720))

    def test_load_adapter_threads_quality(self):
        adapter = load_adapter("tiktok", "@x", quality="720p")
        self.assertEqual(adapter.quality_height, 720)
        adapter2 = load_adapter("youtube", "ch", quality="best")
        self.assertIsNone(adapter2.quality_height)
        with self.assertRaises(ValueError):
            load_adapter("tiktok", "@x", quality="bad")

    def test_tiktok_adapter_builds_capped_format(self):
        adapter = TikTokAdapter("@x", quality="720p")
        fmt = "b[height<={h}][ext=flv]/best[height<={h}]/best".format(h=adapter.quality_height)
        self.assertEqual(fmt, "b[height<=720][ext=flv]/best[height<=720]/best")


class SignalStopTest(unittest.TestCase):
    """SIGTERM 必须即时生效，且先让 ffmpeg 收尾当前分段。

    历史故障：WebUI 点"停止"后任务要 ~30 秒才消失、前端 12 秒即报超时。
    原因：信号处理器常在 curl_cffi/subprocess 的 C 回调里执行，`sys.exit()` 抛出的
    SystemExit 被 C 层吞掉（"Exception ignored from cffi callback"），进程继续轮询，
    直到 systemd TimeoutStopSec（30s）到期被 SIGKILL。
    """

    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="dlr_signal_test_"))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)

    def _spawn_engine(self, body: str) -> subprocess.Popen:
        """在子进程里启动 Engine 并执行 body，等它打印 ready 后返回该进程。"""
        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(PROJECT_ROOT / 'scripts')!r})\n"
            "import ctypes, ctypes.util, subprocess, time\n"
            "from pathlib import Path\n"
            "from dlr.engine import Engine\n"
            f"engine = Engine('tiktok', 'sig.ch', {str(self.base)!r}, detect_interval=30, break_seconds=1)\n"
            "engine.adapter.get_nickname = lambda: None\n"
            + textwrap.dedent(body)
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", script],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(proc.kill)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if line.strip() == "ready":
                return proc
            if not line:
                break
        self.fail("子进程未进入 ready 状态：\n" + (proc.stderr.read() or ""))

    def _assert_exited(self, proc: subprocess.Popen) -> None:
        try:
            rc = proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            _, stderr = proc.communicate(timeout=5)
            self.fail("SIGTERM 后引擎未及时退出：\n" + (stderr or ""))
        self.assertEqual(rc, 0)

    def test_sigterm_exits_promptly_inside_c_callback(self):
        """检测轮询里信号处理器落在 C 回调栈内时，进程也必须立刻退出。

        真实场景：`adapter.detect_stream_url()` 走 curl_cffi，信号在 cffi 回调中被处理；
        `sys.exit()` 无效时会继续跑完 `detect_interval`（生产默认 120–300s）等待，
        表现为"停止不了"。
        """
        proc = self._spawn_engine(
            """
            libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
            comparator = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
            state = {"first": True}

            @comparator
            def _cmp(_a, _b):
                # 回调里打印 ready：此时主线程正在 C 调用栈内执行 python 回调，
                # 等测试发来的 SIGTERM 就在这里被处理。
                if state["first"]:
                    state["first"] = False
                    print("ready", flush=True)
                    time.sleep(1.5)
                return 0

            def detect():
                libc.qsort((ctypes.c_int * 8)(), 8, ctypes.sizeof(ctypes.c_int), _cmp)
                return None  # 未开播 → 引擎将进入 detect_interval 等待

            engine.adapter.detect_stream_url = detect
            engine.run()
            """
        )
        proc.send_signal(signal.SIGTERM)
        self._assert_exited(proc)

    def test_sigterm_finalizes_ffmpeg_before_exit(self):
        """停止时先给 ffmpeg 发送 SIGTERM 并等它退出（MP4 正常收尾），再结束进程。"""
        marker = self.base / "ffmpeg-finalized"
        child_code = textwrap.dedent(
            """
            import signal, sys, time
            from pathlib import Path

            def _done(*_):
                Path(sys.argv[1]).write_text("finalized")
                sys.exit(0)

            signal.signal(signal.SIGTERM, _done)
            time.sleep(120)
            """
        )
        proc = self._spawn_engine(
            f"""
            engine.ffmpeg_proc = subprocess.Popen(
                [sys.executable, "-c", {child_code!r}, {str(marker)!r}],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            print("ready", flush=True)
            time.sleep(120)
            """
        )
        proc.send_signal(signal.SIGTERM)
        self._assert_exited(proc)
        self.assertEqual(marker.read_text(), "finalized")


if __name__ == "__main__":
    unittest.main()
