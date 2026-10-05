"""tiktok_extract 页面解析与 webcast API 的回归测试（不访问真实网络）。

背景（item 加固）：`tiktok_extract.py` 是 TikTok 逆向取流的平台耦合点，
页面结构（SIGI_STATE / __UNIVERSAL_DATA_FOR_REHYDRATION__ / room/info）
随 TikTok 改版漂移，历史上出现过：
- WAF 残页内嵌残缺 SIGI 脚本 → json.loads 抛异常冲出检测主流程；
- 离线页携带上次直播的陈旧 streamData → 误报开播、ffmpeg 秒退。
本文件用真实结构的固定样本锁定解析行为与门禁语义。
"""

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import dlr.adapters.tiktok_extract as mod  # noqa: E402
from dlr.adapters.tiktok_extract import (  # noqa: E402
    _load_netscape_cookies,
    _request_with_retry,
    check_live_via_webcast_api,
    get_room_id_from_sigi,
    get_room_id_from_universal,
)

try:  # 取流网络层依赖 curl_cffi；缺失环境（如最小化镜像）下相关用例自动 skip
    import curl_cffi  # noqa: F401

    HAS_CURL_CFFI = True
except ImportError:  # pragma: no cover
    HAS_CURL_CFFI = False


def sigi_page(payload: object) -> str:
    """包一层直播页的 SIGI_STATE 脚本标签。payload 已是 JSON 字符串时原样嵌入。"""
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return f'<html><script id="SIGI_STATE" type="application/json">{body}</script></html>'


def universal_page(payload: object) -> str:
    body = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    return (
        '<html><script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" '
        f'type="application/json">{body}</script></html>'
    )


def live_sigi(status: int = 2, room_id: str = "7123456789") -> dict:
    return {
        "LiveRoom": {
            "liveRoomUserInfo": {"liveRoom": {"status": status, "roomId": room_id}},
        },
    }


class RoomIdFromSigiTest(unittest.TestCase):
    def test_live_room_returns_room_id_and_status(self):
        self.assertEqual(get_room_id_from_sigi(sigi_page(live_sigi())), ("7123456789", 2))

    def test_offline_without_current_room_keeps_status(self):
        # 离线房即使带 roomId 也原样返回 status=4；调用方以 status==2 为门禁，
        # 不会把它当开播（webcast API 是第二道门禁）。
        self.assertEqual(get_room_id_from_sigi(sigi_page(live_sigi(status=4))), ("7123456789", 4))
        self.assertEqual(
            get_room_id_from_sigi(sigi_page({"LiveRoom": {"liveRoomUserInfo": {"liveRoom": {"status": 4}}}})),
            (None, 4),
        )

    def test_current_room_fallback_marks_live_for_api_recheck(self):
        # 页面级发现语义：CurrentRoom 有 roomId 即视为“可能在播”，
        # 真正的开播门禁由 check_live_via_webcast_api 的 status==2 把守。
        page = sigi_page({"LiveRoom": {}, "CurrentRoom": {"roomId": 999}})
        self.assertEqual(get_room_id_from_sigi(page), ("999", 2))

    def test_missing_script_returns_not_found(self):
        self.assertEqual(get_room_id_from_sigi("<html></html>"), (None, -1))

    def test_malformed_json_does_not_raise(self):
        # WAF 残页：脚本存在但内容截断。此前 json.loads 异常会冲出检测主流程。
        self.assertEqual(get_room_id_from_sigi(sigi_page("{ truncated")), (None, -1))

    def test_non_dict_json_returns_not_found(self):
        self.assertEqual(get_room_id_from_sigi(sigi_page("[1, 2]")), (None, -1))

    def test_non_dict_live_room_does_not_raise(self):
        page = sigi_page({"LiveRoom": "unexpected", "CurrentRoom": {}})
        self.assertEqual(get_room_id_from_sigi(page), (None, 0))

    def test_non_dict_live_room_user_info_does_not_raise(self):
        page = sigi_page({"LiveRoom": {"liveRoomUserInfo": ["nested"]}})
        self.assertEqual(get_room_id_from_sigi(page), (None, 0))

    def test_numeric_status_without_room_id_falls_back(self):
        page = sigi_page({"LiveRoom": {"liveRoomUserInfo": {"liveRoom": {"status": 4}}}})
        self.assertEqual(get_room_id_from_sigi(page), (None, 4))


class RoomIdFromUniversalTest(unittest.TestCase):
    def _scope(self, key: str, room_id: object) -> str:
        return universal_page({"__DEFAULT_SCOPE__": {key: {"userInfo": {"user": {"roomId": room_id}}}}})

    def test_primary_key_preferred(self):
        page = universal_page({
            "__DEFAULT_SCOPE__": {
                "webcast.user-detail": {"userInfo": {"user": {"roomId": "111"}}},
                "webcast-sse.user-detail": {"userInfo": {"user": {"roomId": "222"}}},
            }
        })
        self.assertEqual(get_room_id_from_universal(page), "111")

    def test_sse_and_webapp_variants(self):
        self.assertEqual(get_room_id_from_universal(self._scope("webcast-sse.user-detail", "222")), "222")
        self.assertEqual(get_room_id_from_universal(self._scope("webapp.user-detail", "333")), "333")

    def test_numeric_room_id_stringified(self):
        self.assertEqual(get_room_id_from_universal(self._scope("webcast.user-detail", 42)), "42")

    def test_empty_room_id_returns_none(self):
        self.assertEqual(get_room_id_from_universal(self._scope("webcast.user-detail", "")), None)

    def test_missing_keys_and_script_return_none(self):
        self.assertIsNone(get_room_id_from_universal(universal_page({"__DEFAULT_SCOPE__": {}})))
        self.assertIsNone(get_room_id_from_universal("<html></html>"))

    def test_malformed_json_does_not_raise(self):
        self.assertIsNone(get_room_id_from_universal(universal_page("{ truncated")))

    def test_non_dict_shapes_do_not_raise(self):
        cases = [
            universal_page("[1]"),
            universal_page({"__DEFAULT_SCOPE__": "oops"}),
            universal_page({"__DEFAULT_SCOPE__": {"webcast.user-detail": "oops"}}),
            universal_page({"__DEFAULT_SCOPE__": {"webcast.user-detail": {"userInfo": "oops"}}}),
            universal_page({"__DEFAULT_SCOPE__": {"webcast.user-detail": {"userInfo": {"user": "oops"}}}}),
        ]
        for page in cases:
            self.assertIsNone(get_room_id_from_universal(page), page[:60])


class _FakeResponse:
    def __init__(self, data: object = None, *, bad_json: bool = False) -> None:
        self._data = data
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("invalid json body")
        return self._data


class _FakeSession:
    def __init__(self, response: _FakeResponse | None) -> None:
        self._response = response
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        return self._response


@unittest.skipUnless(HAS_CURL_CFFI, "curl_cffi 未安装")
class CheckLiveViaWebcastApiTest(unittest.TestCase):
    FLV = {
        "ORIGIN": "https://cdn/live.flv",
        "FULL_HD1": "https://cdn/1080.flv",
        "HD1": "https://cdn/720.flv",
        "SD2": "https://cdn/360.flv",
    }

    def _check(self, payload: object, max_height: int | None = None, *, bad_json=False):
        session = _FakeSession(_FakeResponse(payload, bad_json=bad_json))
        return check_live_via_webcast_api(session, "7123", max_height), session

    def test_requests_room_info_with_room_id(self):
        _, session = self._check({"status_code": 0, "data": {"status": 4}})
        url, kwargs = session.calls[0]
        self.assertIn("webcast/room/info", url)
        self.assertEqual(kwargs["params"]["room_id"], "7123")

    def test_nonzero_status_code_rejected(self):
        url, _ = self._check({"status_code": 10006, "data": {}})
        self.assertIsNone(url)

    def test_stale_stream_rejected_when_room_offline(self):
        # 陈旧流门禁：离线房（status!=2）即使带完整 stream_url 也必须拒绝。
        url, _ = self._check(
            {"status_code": 0, "data": {"status": 4, "stream_url": {"flv_pull_url": self.FLV}}}
        )
        self.assertIsNone(url)

    def test_origin_quality_when_no_limit(self):
        url, _ = self._check(
            {"status_code": 0, "data": {"status": 2, "stream_url": {"flv_pull_url": self.FLV}}}
        )
        self.assertEqual(url, "https://cdn/live.flv")

    def test_height_limited_quality_pick(self):
        url, _ = self._check(
            {"status_code": 0, "data": {"status": 2, "stream_url": {"flv_pull_url": self.FLV}}},
            max_height=720,
        )
        self.assertEqual(url, "https://cdn/720.flv")

    def test_falls_back_to_lowest_when_all_exceed_limit(self):
        url, _ = self._check(
            {"status_code": 0, "data": {"status": 2, "stream_url": {"flv_pull_url": self.FLV}}},
            max_height=144,
        )
        self.assertEqual(url, "https://cdn/360.flv")

    def test_rtmp_fallback_when_no_flv(self):
        payload = {
            "status_code": 0,
            "data": {"status": 2, "stream_url": {"flv_pull_url": {}, "rtmp_pull_url": "rtmp://x/live"}},
        }
        # 非 http 的 rtmp 会被跳过；hls 兜底
        url, _ = self._check(payload)
        self.assertIsNone(url)
        payload["data"]["stream_url"]["hls_pull_url"] = "https://cdn/live.m3u8"
        url, _ = self._check(payload)
        self.assertEqual(url, "https://cdn/live.m3u8")

    def test_string_stream_url_accepted(self):
        url, _ = self._check(
            {"status_code": 0, "data": {"status": 2, "stream_url": "https://cdn/direct.flv"}}
        )
        self.assertEqual(url, "https://cdn/direct.flv")

    def test_room_level_rtmp_fallback_when_stream_url_missing(self):
        url, _ = self._check(
            {"status_code": 0, "data": {"status": 2, "rtmp_pull_url": "rtmp://x/room"}}
        )
        self.assertIsNone(url)  # rtmp 非 http 拒绝
        url, _ = self._check(
            {"status_code": 0, "data": {"status": 2, "hls_pull_url": "https://cdn/room.m3u8"}}
        )
        self.assertEqual(url, "https://cdn/room.m3u8")

    def test_bad_json_body_returns_none(self):
        url, _ = self._check({}, bad_json=True)
        self.assertIsNone(url)

    def test_request_failure_returns_none(self):
        with mock.patch.object(mod, "_request_with_retry", return_value=None):
            self.assertIsNone(check_live_via_webcast_api(_FakeSession(None), "7123"))


@unittest.skipUnless(HAS_CURL_CFFI, "curl_cffi 未安装")
class RequestWithRetryTest(unittest.TestCase):
    def test_retries_transient_errors_then_succeeds(self):
        sentinel = object()

        class FlakySession:
            def __init__(self) -> None:
                self.attempts = 0

            def get(self, url, **kwargs):
                self.attempts += 1
                if self.attempts < 3:
                    raise OSError("connection reset")
                return sentinel

        session = FlakySession()
        with mock.patch.object(mod.time, "sleep") as sleep:
            result = _request_with_retry(session, "https://x", attempts=3, base_delay=0.01)
        self.assertIs(result, sentinel)
        self.assertEqual(session.attempts, 3)
        self.assertEqual(sleep.call_count, 2)  # 指数退避：第 1、2 次失败后各睡一次

    def test_gives_up_after_exhausting_attempts(self):
        class DeadSession:
            def get(self, url, **kwargs):
                raise OSError("refused")

        with mock.patch.object(mod.time, "sleep"):
            self.assertIsNone(_request_with_retry(DeadSession(), "https://x", attempts=2))

    def test_respects_max_delay(self):
        class DeadSession:
            def get(self, url, **kwargs):
                raise OSError("refused")

        with mock.patch.object(mod.time, "sleep") as sleep:
            _request_with_retry(
                DeadSession(), "https://x", attempts=4, base_delay=1.0, max_delay=3.0
            )
        delays = [call.args[0] for call in sleep.call_args_list]
        self.assertEqual(delays, [1.0, 2.0, 3.0])


class NetscapeCookieLoadingTest(unittest.TestCase):
    class _Cookies:
        def __init__(self) -> None:
            self.loaded = []

        def set(self, name, value, domain=None, path=None):
            self.loaded.append((name, value, domain, path))

    class _Session:
        def __init__(self) -> None:
            self.cookies = NetscapeCookieLoadingTest._Cookies()

    def test_parses_valid_lines_and_skips_noise(self):
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write(
                "# Netscape HTTP Cookie File\n"
                "\n"
                ".tiktok.com\tTRUE\t/\tTRUE\t1893456000\tsessionid\tabc123\n"
                "too\tfew\tfields\n"
                "www.tiktok.com\tFALSE\t/live\tFALSE\t1893456000\tttwid\txyz\n"
            )
            path = fh.name
        session = self._Session()
        _load_netscape_cookies(session, path)
        self.assertEqual(
            session.cookies.loaded,
            [
                ("sessionid", "abc123", "tiktok.com", "/"),
                ("ttwid", "xyz", "www.tiktok.com", "/live"),
            ],
        )

    def test_missing_or_empty_path_is_noop(self):
        session = self._Session()
        _load_netscape_cookies(session, None)
        _load_netscape_cookies(session, "/definitely/missing/cookies.txt")
        self.assertEqual(session.cookies.loaded, [])


class GetStreamUrlRobustnessTest(unittest.TestCase):
    def _page_response(self, text: str):
        return mock.Mock(text=text)

    def test_malformed_sigi_page_returns_none_without_raising(self):
        """端到端：残缺 SIGI 的页面不得让 get_stream_url 抛异常（整轮检测崩掉）。"""
        response = self._page_response(sigi_page("{ truncated"))
        with (
            mock.patch.object(mod, "_request_with_retry", return_value=response),
            mock.patch.object(mod, "_get_stream_url_with_browser") as browser,
        ):
            url = mod.get_stream_url(
                "someone", try_ytdlp=False, allow_browser=False
            )
        self.assertIsNone(url)
        browser.assert_not_called()

    def test_waf_challenge_page_does_not_spam_browser_when_disallowed(self):
        challenge = "<html>please wait ... slardar</html>"
        with (
            mock.patch.object(mod, "_request_with_retry", return_value=self._page_response(challenge)),
            mock.patch.object(mod, "_get_stream_url_with_browser") as browser,
        ):
            url = mod.get_stream_url("someone", try_ytdlp=False, allow_browser=False)
        self.assertIsNone(url)
        browser.assert_not_called()




class DetectionLogTest(unittest.TestCase):
    def test_only_numeric_and_boolean_response_fields_are_logged(self):
        lines = []
        diag = mod.DetectionDiagnostics(lines.append)
        diag.event("page", "parsed", live_status="SECRET", room_id_present=True,
                   http_status=403, room_id="SECRET", cookie="SECRET", url="SECRET")
        self.assertNotIn("SECRET", "\n".join(lines))
        self.assertIn("http_status=403", lines[0])
        self.assertIn("room_id_present=True", lines[0])

    def test_uncertain_or_live_evidence_overrides_offline(self):
        for result, fields in [("no_stream", {}), ("room_status", {"live_status": 2})]:
            diag = mod.DetectionDiagnostics(lambda line: None)
            diag.event("page", "offline")
            diag.event("webcast", result, **fields)
            self.assertIn("检测/提取失败", diag.failure_reason)


@unittest.skipUnless(HAS_CURL_CFFI, "curl_cffi 未安装")
class DetectionFlowLogTest(unittest.TestCase):
    def detect(self, response, *, browser=False, rendered=None, api=None):
        from dlr.adapters.tiktok import TikTokAdapter
        adapter = TikTokAdapter("example", cookies="SECRET_COOKIE_PATH")
        if browser:
            adapter._lightweight_misses = 2
        lines = []
        adapter.diagnostic_log = lines.append
        adapter.run_capture = mock.Mock(return_value=None)
        with mock.patch.object(mod, "_request_with_retry", side_effect=[None, response] + (api or [])), \
             mock.patch.object(mod, "_load_netscape_cookies"), \
             mock.patch.object(mod, "_get_stream_url_with_browser", return_value=rendered) as render:
            stream = adapter.detect_stream_url()
        return stream, adapter, "\n".join(lines), render

    def page(self, text, status=200):
        return mock.Mock(text=text, status_code=status)

    def api(self, data):
        response = _FakeResponse(data)
        response.status_code = 200
        return response

    def test_confirmed_offline_and_skipped_fallbacks(self):
        stream, adapter, logs, render = self.detect(self.page(sigi_page(live_sigi(status=4))),
            api=[self.api({"status_code": 0, "data": {"status": 4}})])
        self.assertIsNone(stream)
        self.assertIn("确认未开播", adapter.last_detect_error)
        self.assertIn("stage=browser result=skipped", logs)
        self.assertIn("stage=ytdlp result=skipped", logs)
        self.assertIn("stage=round result=offline", logs)
        render.assert_not_called()

    def test_waf_http_and_network_failures_are_not_offline(self):
        for page, expected in [(self.page("please wait SECRET_RESPONSE"), "page_unrecognized"),
                               (self.page("SECRET_RESPONSE", 403), "http_error"),
                               (None, "network_error"),
                               (self.page(sigi_page("{SECRET_RESPONSE")), "page_unrecognized")]:
            with self.subTest(expected=expected):
                stream, adapter, logs, _ = self.detect(page)
                self.assertIsNone(stream)
                self.assertIn("检测/提取失败", adapter.last_detect_error)
                self.assertIn(f"result={expected}", logs)
                self.assertNotIn("SECRET", logs)

    def test_api_no_stream_business_error_and_invalid_payload(self):
        cases = [({"status_code": 0, "data": {"status": 2}}, "no_stream"),
                 ({"status_code": 10006, "message": "SECRET"}, "business_error"),
                 (["SECRET"], "invalid_payload"),
                 ({"status_code": 0, "data": "SECRET"}, "invalid_payload")]
        for payload, result in cases:
            with self.subTest(result=result):
                stream, adapter, logs, _ = self.detect(self.page(sigi_page(live_sigi())), api=[self.api(payload)])
                self.assertIsNone(stream)
                self.assertIn("检测/提取失败", adapter.last_detect_error)
                self.assertIn(f"stage=webcast result={result}", logs)
                self.assertNotIn("SECRET", logs)
                self.assertNotIn("7123456789", logs)

    def test_browser_success_and_failure(self):
        for url in ["https://cdn/live.flv?signature=SECRET", None]:
            with self.subTest(success=bool(url)):
                stream, adapter, logs, render = self.detect(self.page("please wait SECRET"), browser=True, rendered=url)
                self.assertEqual(stream, url)
                self.assertEqual(render.call_count, 1)
                self.assertIn("stage=browser result=started", logs)
                self.assertIn("stage=round result=success" if url else "stage=round result=detection_failed", logs)
                self.assertNotIn("SECRET", logs)
                if url:
                    self.assertIsNone(adapter.last_detect_error)

    def test_api_success_never_logs_signed_url_or_response(self):
        url = "https://cdn/live.flv?signature=SECRET"
        stream, adapter, logs, _ = self.detect(self.page(sigi_page(live_sigi())), api=[self.api({
            "status_code": 0, "data": {"status": 2, "stream_url": url}, "cookie": "SECRET"})])
        self.assertEqual(stream, url)
        self.assertIsNone(adapter.last_detect_error)
        self.assertIn("stage=webcast result=success", logs)
        self.assertNotIn("SECRET", logs)


class YtdlpLogTest(unittest.TestCase):
    def test_failure_categories_and_success_are_safe(self):
        import subprocess
        from dlr.adapters.tiktok import TikTokAdapter
        results = [
            (subprocess.TimeoutExpired(["SECRET"], 1, stderr="SECRET"), "timeout"),
            (OSError("SECRET"), "execution_error"),
            (subprocess.CompletedProcess([], 1, "SECRET", "SECRET"), "process_error"),
            (subprocess.CompletedProcess([], 0, "", "SECRET"), "empty_output"),
            (subprocess.CompletedProcess([], 0, "https://cdn/live?token=SECRET\n", "SECRET"), "success"),
        ]
        for result, expected in results:
            with self.subTest(expected=expected):
                lines = []
                diag = mod.DetectionDiagnostics(lines.append)
                kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
                with mock.patch("dlr.adapters.tiktok.subprocess.run", **kwargs):
                    url = TikTokAdapter("example").run_capture(["SECRET"], diagnostics=diag)
                self.assertEqual(bool(url), expected == "success")
                self.assertIn(f"result={expected}", "\n".join(lines))
                self.assertNotIn("SECRET", "\n".join(lines))


@unittest.skipUnless(HAS_CURL_CFFI, "curl_cffi 未安装")
class AdditionalDetectionFailureTest(unittest.TestCase):
    def test_api_http_invalid_json_and_network_categories(self):
        response = mock.Mock(status_code=503, text="SECRET_RESPONSE")
        bad_json = _FakeResponse(bad_json=True)
        bad_json.status_code = 200
        for response, expected in [(response, "http_error"), (bad_json, "invalid_json"), (None, "network_error")]:
            with self.subTest(expected=expected):
                lines = []
                diag = mod.DetectionDiagnostics(lines.append)
                with mock.patch.object(mod, "_request_with_retry", return_value=response):
                    self.assertIsNone(check_live_via_webcast_api(None, "SECRET_ROOM", diagnostics=diag))
                self.assertIn(f"result={expected}", "\n".join(lines))
                self.assertNotIn("SECRET", "\n".join(lines))

    def test_browser_response_and_exception_are_not_logged(self):
        lines = []
        diag = mod.DetectionDiagnostics(lines.append)
        with mock.patch("dlr.browserd.render_document", return_value="SECRET_RESPONSE"):
            self.assertIsNone(mod._get_stream_url_with_browser("example", diagnostics=diag))
        self.assertIn("result=page_unrecognized", "\n".join(lines))
        response = mock.Mock(status_code=200, text="please wait SECRET_RESPONSE")
        with mock.patch.object(mod, "_request_with_retry", side_effect=[None, response]), \
             mock.patch.object(mod, "_get_stream_url_with_browser", side_effect=RuntimeError("SECRET_EXCEPTION")):
            self.assertIsNone(mod.get_stream_url("example", try_ytdlp=False, diagnostics=diag))
        self.assertIn("stage=browser result=error", "\n".join(lines))
        self.assertNotIn("SECRET", "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
