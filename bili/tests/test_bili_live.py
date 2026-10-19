"""live.py 单元测试（纯函数 + mock 网络，不做真实请求）。

被测模块来源见 ``live.py`` 模块文档（上游 Zarosmm/obs-bilibili-stream，GPL-2.0）。
"""

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import live as bili_live  # noqa: E402


class AppsignTest(unittest.TestCase):
    def test_sorts_params_and_appends_sign(self):
        signed = bili_live.appsign([("b", "2"), ("a", "1")], "K", "S")
        query = "a=1&b=2&appkey=K"
        expect = f"{query}&sign={hashlib.md5((query + 'S').encode()).hexdigest()}"
        self.assertEqual(signed, expect)

    def test_sign_is_md5_of_query_plus_secret(self):
        signed = bili_live.appsign([("room_id", "123")], bili_live.APP_KEY, bili_live.APP_SECRET)
        head, sign = signed.rsplit("&sign=", 1)
        self.assertIn("appkey=aae92bc66f3edfab", head)
        self.assertEqual(sign, hashlib.md5((head + bili_live.APP_SECRET).encode()).hexdigest())


class CookieTest(unittest.TestCase):
    def test_extract_cookie_value(self):
        cookies = "SESSDATA=abc; bili_jct=xyz; DedeUserID=123;"
        self.assertEqual(bili_live.extract_cookie_value(cookies, "SESSDATA"), "abc")
        self.assertEqual(bili_live.extract_cookie_value(cookies, "bili_jct"), "xyz")
        self.assertEqual(bili_live.extract_cookie_value(cookies, "missing"), "")

    def test_parse_set_cookies(self):
        seen = []

        class Headers:
            def get_all_matching_headers(self, name):
                seen.append(name)
                return [
                    "Set-Cookie: SESSDATA=abc; Path=/; HttpOnly\r\n",
                    "Set-Cookie: bili_jct=xyz; Path=/\r\n",
                    "Set-Cookie: buvid3=nouse\r\n",
                ]

        self.assertEqual(
            bili_live.parse_set_cookies(Headers()),
            "SESSDATA=abc; bili_jct=xyz; buvid3=nouse",
        )
        self.assertEqual(seen, ["Set-cookie"])

    def test_extract_url_param(self):
        url = "https://x.test/cb?SESSDATA=abc&bili_jct=xyz"
        self.assertEqual(bili_live.extract_url_param(url, "SESSDATA"), "abc")
        self.assertEqual(bili_live.extract_url_param(url, "missing"), "")


class SessionTest(unittest.TestCase):
    def test_save_load_roundtrip_with_0600(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sess.json"
            bili_live.save_session(path, {"cookies": "a=b", "room_id": "1"})
            self.assertEqual(bili_live.load_session(path)["room_id"], "1")
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")

    def test_load_missing_returns_empty(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(bili_live.load_session(Path(tmp) / "none.json"), {})


class StartLiveTest(unittest.TestCase):
    def test_face_auth_60024_reports_qr(self):
        calls = [
            ({"code": 0, "data": {"build": 100, "curr_version": "1.0"}}, ""),
            ({"code": 60024, "message": "need face", "data": {"qr": "https://face/qr"}}, ""),
        ]
        with mock.patch.object(bili_live, "_request", side_effect=calls):
            with self.assertRaises(bili_live.BiliError) as ctx:
                bili_live.start_live("ck", "123", "csrf", 86)
        self.assertIn("https://face/qr", str(ctx.exception))

    def test_success_returns_rtmp(self):
        calls = [
            ({"code": 0, "data": {"build": 100, "curr_version": "1.0"}}, ""),
            (
                {
                    "code": 0,
                    "data": {"rtmp": {"addr": "rtmp://live/", "code": "key123"}},
                },
                "",
            ),
        ]
        with mock.patch.object(bili_live, "_request", side_effect=calls):
            addr, code = bili_live.start_live("ck", "123", "csrf", 86)
        self.assertEqual((addr, code), ("rtmp://live/", "key123"))

    def test_form_omits_build_param(self):
        # 回归：含 build 签名必回 -3（2026-09-06 实测），表单不得带 build
        seen = {}

        def fake_request(url, *, cookies="", data=None, timeout=15):
            if data is not None:
                seen["form"] = data
            if "startLive" in url:
                return ({"code": 0, "data": {"rtmp": {"addr": "rtmp://live/", "code": "k"}}}, "")
            return ({"code": 0, "data": {"build": 11025, "curr_version": "8.5.0.11025"}}, "")

        with mock.patch.object(bili_live, "_request", side_effect=fake_request):
            bili_live.start_live("ck", "123", "csrf", 646)
        self.assertNotIn("build=", seen["form"])
        self.assertIn("area_v2=646", seen["form"])


class CoverUploadTest(unittest.TestCase):
    def test_upload_uses_base64_form_and_accepts_url_response(self):
        with tempfile.NamedTemporaryFile(suffix=".png") as image:
            image.write(b"png-data")
            image.flush()
            seen = {}

            def fake_request(url, *, cookies="", data=None, timeout=15):
                seen["url"], seen["form"] = url, data
                return ({"code": 0, "data": {"url": "https://img.example/cover.jpg"}}, "")

            with mock.patch.object(bili_live, "_request", side_effect=fake_request):
                result = bili_live.upload_cover("ck", "csrf", Path(image.name))
        self.assertEqual(result, "https://img.example/cover.jpg")
        self.assertEqual(seen["url"], bili_live.COVER_UPLOAD_URL)
        fields = dict(urllib.parse.parse_qsl(seen["form"]))
        self.assertEqual(fields["csrf"], "csrf")
        self.assertTrue(fields["cover"].startswith("data:image/png;base64,"))


class QrRenderTest(unittest.TestCase):
    def test_square_with_quiet_zone_and_deterministic(self):
        first = bili_live.render_qr_terminal("https://example.com")
        second = bili_live.render_qr_terminal("https://example.com")
        self.assertEqual(first, second)
        lines = first.split("\n")
        self.assertGreater(len(lines), 20)  # 版本≥1 含边框
        widths = {len(line) for line in lines}
        self.assertEqual(len(widths), 1)  # 等宽
        self.assertTrue(lines[0].strip() == "")  # 顶部静区
        self.assertTrue(lines[-1].strip() == "")  # 底部静区
        self.assertTrue(all(line.startswith("  ") and line.endswith("  ") for line in lines))  # 左右静区
        self.assertIn("██", first)


class ResolveRoomTest(unittest.TestCase):
    """房间号只服务开播；纯投稿账号没有直播间，不该让登录失败。"""

    def _resolve(self, payload):
        with mock.patch.object(bili_live, "_request", return_value=(payload, "")):
            return bili_live.resolve_room("DedeUserID=42; bili_jct=x;")

    def test_normal_account(self):
        self.assertEqual(self._resolve({"code": 0, "message": "ok", "data": {"room_id": 123}}), ("123", "x"))

    def test_account_without_live_room_raises_readable_error(self):
        # 实测：新注册账号回 code=404 + data=[]；message 字段此时也是 "ok"
        with self.assertRaises(bili_live.BiliError) as ctx:
            self._resolve({"code": 404, "message": "ok", "msg": "ok", "data": []})
        msg = str(ctx.exception)
        self.assertIn("没有直播间", msg)
        self.assertIn("404", msg)
        self.assertNotIn("失败：ok", msg)  # 旧写法会输出这个无信息量的提示

    def test_error_reports_code_and_data_not_just_message(self):
        with self.assertRaises(bili_live.BiliError) as ctx:
            self._resolve({"code": -1, "message": "ok", "data": None})
        self.assertIn("code=-1", str(ctx.exception))

    def test_empty_room_id_raises(self):
        with self.assertRaises(bili_live.BiliError) as ctx:
            self._resolve({"code": 0, "message": "ok", "data": {"room_id": "0"}})
        self.assertIn("room_id 为空", str(ctx.exception))

    def test_data_not_dict_raises(self):
        with self.assertRaises(bili_live.BiliError):
            self._resolve({"code": 0, "message": "ok", "data": []})


class LoginWithoutRoomTest(unittest.TestCase):
    """实测过的 bug：投稿账号没有直播间时，整次登录被作废（save_session 走不到）。"""

    def _run_login(self, resolve_payload):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            argv = ["--session", str(path), "login", "--timeout", "1", "--poll-interval", "0"]
            with mock.patch.object(bili_live, "qr_generate", return_value=("u", "k")), \
                    mock.patch.object(bili_live, "render_qr_terminal", return_value="qr"), \
                    mock.patch.object(bili_live, "qr_poll", return_value=({"code": 0}, "SESSDATA=s; bili_jct=j; DedeUserID=7;")), \
                    mock.patch.object(bili_live, "check_login", return_value=(True, "7")), \
                    mock.patch.object(bili_live, "_request", return_value=(resolve_payload, "")):
                with contextlib.redirect_stdout(io.StringIO()):  # 吞掉扫码提示噪音
                    rc = bili_live.main(argv)
            return rc, (json.loads(path.read_text(encoding="utf-8")) if path.exists() else None)

    def test_session_is_saved_even_without_live_room(self):
        rc, saved = self._run_login({"code": 404, "message": "ok", "data": []})
        self.assertEqual(rc, 0)
        self.assertIsNotNone(saved, "会话未落盘——登录被作废了")
        self.assertEqual(saved["mid"], "7")
        self.assertEqual(saved["room_id"], "")      # 留空，首次开播时再补
        self.assertEqual(saved["csrf_token"], "j")  # csrf 不依赖房间号，必须拿到

    def test_session_saved_with_room_when_available(self):
        rc, saved = self._run_login({"code": 0, "message": "ok", "data": {"room_id": 555}})
        self.assertEqual(rc, 0)
        self.assertEqual(saved["room_id"], "555")


class ParserTest(unittest.TestCase):
    # 曾经的坑：--account/--session 只能写在子命令之前，写在后面直接报
    # "unrecognized arguments"。文档里给的却是错误用法。现在两种位置都支持。

    def test_account_accepted_before_and_after_subcommand(self):
        for argv in (["--account", "upload", "login"], ["login", "--account", "upload"]):
            args = bili_live.build_parser().parse_args(argv)
            self.assertEqual(args.account, "upload", argv)
            self.assertEqual(args.cmd, "login", argv)

    def test_omitted_common_args_leave_no_attribute(self):
        # SUPPRESS 语义：未给出时属性不存在，由 main() 补默认值
        args = bili_live.build_parser().parse_args(["status"])
        self.assertFalse(hasattr(args, "account"))
        self.assertFalse(hasattr(args, "session"))

    def test_session_before_subcommand_not_clobbered(self):
        args = bili_live.build_parser().parse_args(["--session", "/tmp/a.json", "status"])
        self.assertEqual(args.session, Path("/tmp/a.json"))

    def test_every_subcommand_accepts_common_args(self):
        for argv in (["accounts"], ["use", "x"], ["login"], ["status"], ["areas"],
                     ["is-live"], ["stop"]):
            args = bili_live.build_parser().parse_args(argv + ["--account", "live"])
            self.assertEqual(args.account, "live", argv)


if __name__ == "__main__":
    unittest.main()
