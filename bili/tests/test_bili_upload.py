"""upload.py 单元测试（纯函数 + mock 网络，不做真实请求）。"""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import upload as bili_upload  # noqa: E402
from live import BiliError  # noqa: E402

COOKIE = "SESSDATA=abc; bili_jct=csrf123; DedeUserID=42;"


class TruncateTitleTest(unittest.TestCase):
    def test_short_title_untouched(self):
        self.assertEqual(bili_upload.truncate_title("abc"), "abc")

    def test_exactly_at_limit_untouched(self):
        title = "a" * bili_upload.MAX_TITLE
        self.assertEqual(bili_upload.truncate_title(title), title)

    def test_over_limit_truncates_by_char_and_keeps_total(self):
        title = "a" * (bili_upload.MAX_TITLE + 10)
        got = bili_upload.truncate_title(title)
        self.assertEqual(len(got), bili_upload.MAX_TITLE)
        self.assertTrue(got.endswith("..."))


class HumanSizeTest(unittest.TestCase):
    def test_kb_below_one_mb(self):
        self.assertEqual(bili_upload._human_size(954 * 1024), "954 KB")

    def test_mb_above_one_mb(self):
        self.assertEqual(bili_upload._human_size(39 * 1024 * 1024 + 900 * 1024), "39.9 MB")


class ExpandInputsTest(unittest.TestCase):
    def test_dir_expands_sorted_mp4_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b.mp4").write_bytes(b"")
            (root / "a.mp4").write_bytes(b"")
            (root / "note.txt").write_bytes(b"")
            nested = root / "sub"
            nested.mkdir()
            (nested / "c.mp4").write_bytes(b"")
            got = [p.name for p in bili_upload.expand_inputs([str(root)])]
            self.assertEqual(got, ["a.mp4", "b.mp4"])

    def test_explicit_file_passes_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.mp4"
            path.write_bytes(b"")
            self.assertEqual(bili_upload.expand_inputs([str(path)]), [path])

    def test_missing_input_raises(self):
        with self.assertRaises(BiliError):
            bili_upload.expand_inputs(["/nope/nothing.mp4"])

    def test_dir_without_mp4_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(BiliError):
                bili_upload.expand_inputs([tmp])


class BuildPayloadTest(unittest.TestCase):
    def setUp(self):
        self.videos = [
            {"filename": "n001", "biz_id": 11, "size": 1},
            {"filename": "n002", "biz_id": 22, "size": 2},
        ]

    def test_maps_filename_and_cid(self):
        payload = bili_upload.build_payload(self.videos, title="T", tid=160, copyright=1)
        self.assertEqual(
            [(v["filename"], v["cid"]) for v in payload["videos"]], [("n001", 11), ("n002", 22)]
        )
        self.assertEqual(payload["tid"], 160)
        self.assertEqual(payload["desc_format_id"], 9999)
        self.assertEqual(payload["web_os"], 3)
        self.assertNotIn("source", payload)

    def test_reprint_requires_source(self):
        with self.assertRaises(BiliError):
            bili_upload.build_payload(self.videos, title="T", tid=160, copyright=2)
        payload = bili_upload.build_payload(
            self.videos, title="T", tid=160, copyright=2, source="marumo rea"
        )
        self.assertEqual(payload["source"], "marumo rea")

    def test_only_self_and_tid_v2_are_opt_in(self):
        plain = bili_upload.build_payload(self.videos, title="T", tid=160, copyright=1)
        self.assertNotIn("is_only_self", plain)
        self.assertNotIn("human_type2", plain)
        extra = bili_upload.build_payload(
            self.videos, title="T", tid=160, copyright=1, only_self=True, tid_v2=1030
        )
        self.assertEqual(extra["is_only_self"], 1)
        self.assertEqual(extra["human_type2"], 1030)

    def test_part_titles_override_manuscript_title(self):
        videos = bili_upload._apply_part_titles(self.videos, "2026-09-19 直播回放")
        self.assertEqual(
            [v["title"] for v in videos], ["2026-09-19 直播回放 01", "2026-09-19 直播回放 02"]
        )

    def test_part_title_prefix_optional(self):
        self.assertEqual(bili_upload._apply_part_titles(self.videos, None), self.videos)

    def test_empty_video_list_raises(self):
        with self.assertRaises(BiliError):
            bili_upload.build_payload([], title="T", tid=160, copyright=1)


class StateTest(unittest.TestCase):
    def test_missing_state_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = bili_upload.load_state(Path(tmp) / "none.json")
            self.assertEqual(state["videos"], [])

    def test_roundtrip_with_0600(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            bili_upload.save_state(path, {"videos": [{"filename": "n1", "biz_id": 5}]})
            loaded = bili_upload.load_state(path)
            self.assertEqual(loaded["videos"][0]["biz_id"], 5)
            self.assertEqual(loaded["version"], bili_upload.STATE_VERSION)
            self.assertIn("updated_at", loaded)
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")

    def test_corrupt_state_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(BiliError):
                bili_upload.load_state(path)

    def test_wrong_shape_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(json.dumps({"videos": "nope"}), encoding="utf-8")
            with self.assertRaises(BiliError):
                bili_upload.load_state(path)


class PreuploadTest(unittest.TestCase):
    def test_uses_upos_profile_and_passes_size(self):
        with mock.patch.object(bili_upload, "_json_call", return_value={"OK": 1}) as call:
            bili_upload.Uploader(COOKIE).preupload("clip.mp4", 4096)
        url = call.call_args.args[0]
        self.assertTrue(url.startswith(bili_upload.PREUPLOAD_URL + "?"))
        for expect in ("name=clip.mp4", "r=upos", "profile=ugcupos%2Fbup", "size=4096"):
            self.assertIn(expect, url)


class UploadFlowTest(unittest.TestCase):
    """走完整上传链路，断言 URL 拼接、分片参数与合并 parts 的顺序。"""

    PREUPLOAD = {
        "OK": 1,
        "auth": "ak=1&sign=abc",
        "biz_id": 777,
        "chunk_size": 4,
        "chunk_retry": 2,
        # B 站的 endpoint 自带协议相对前缀，upos_uri 自带 upos:// 协议头
        "endpoint": "//upos-cs-upcdntxa.bilivideo.com",
        "upos_uri": "upos://ugcever/n260928ad1t7.mp4",
    }

    def setUp(self):
        self.calls = []
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "clip.mp4"
        self.path.write_bytes(b"x" * 10)  # 10 字节 / 4 字节分片 = 3 片

    def tearDown(self):
        self.tmp.cleanup()

    def _fake_http(self, url, *, method="GET", cookies="", data=None, headers=None, timeout=None):
        self.calls.append({"url": url, "method": method, "data": data, "headers": headers or {}})
        if "preupload" in url:
            return 200, {}, json.dumps(self.PREUPLOAD).encode()
        if method == "POST" and "uploads" in url:
            return 200, {}, b'{"OK":1,"upload_id":"uid-1"}'
        if method == "PUT":
            return 200, {"etag": '"tag-%s"' % url.split("partNumber=")[1].split("&")[0]}, b""
        return 200, {}, b'{"OK":1}'  # 合并

    def _run(self):
        with mock.patch.object(bili_upload, "_http", side_effect=self._fake_http):
            return bili_upload.Uploader(COOKIE).upload(self.path, limit=1)

    def test_returns_filename_stem_and_cid(self):
        record = self._run()
        self.assertEqual(record["filename"], "n260928ad1t7")  # 无后缀，提交稿件要用
        self.assertEqual(record["biz_id"], 777)
        self.assertEqual(record["size"], 10)
        self.assertEqual(record["path"], str(self.path))

    def test_upos_url_joins_host_and_path_with_single_slash(self):
        self._run()
        puts = [c for c in self.calls if c["method"] == "PUT"]
        self.assertTrue(puts)
        for call in puts:
            self.assertTrue(
                call["url"].startswith("https://upos-cs-upcdntxa.bilivideo.com/ugcever/n260928ad1t7.mp4?"),
                call["url"],
            )

    def test_part_offsets_and_etags(self):
        self._run()
        puts = [c for c in self.calls if c["method"] == "PUT"]
        self.assertEqual(len(puts), 3)  # ceil(10 / 4)
        self.assertEqual([len(c["data"]) for c in puts], [4, 4, 2])
        for index, call in enumerate(puts):
            self.assertIn(f"partNumber={index + 1}", call["url"])
            self.assertIn("chunks=3", call["url"])
            self.assertIn(f"chunk={index}", call["url"])
            self.assertIn("total=10", call["url"])
            self.assertEqual(call["headers"]["X-Upos-Auth"], "ak=1&sign=abc")

    def test_merge_sends_ordered_parts(self):
        self._run()
        # 登记上传的 POST 也带 output=json，靠 name= 区分合并请求
        merge = [c for c in self.calls if c["method"] == "POST" and "name=clip.mp4" in c["url"]]
        self.assertEqual(len(merge), 1)
        parts = json.loads(merge[0]["data"])["parts"]
        self.assertEqual([p["partNumber"] for p in parts], [1, 2, 3])
        self.assertEqual([p["eTag"] for p in parts], ["tag-1", "tag-2", "tag-3"])
        self.assertIn("uploadId=uid-1", merge[0]["url"])
        self.assertIn("biz_id=777", merge[0]["url"])

    def test_failed_part_raises_after_retries(self):
        def always_500(url, **kwargs):
            self.calls.append({"url": url, "method": kwargs.get("method", "GET")})
            if "preupload" in url:
                return 200, {}, json.dumps(self.PREUPLOAD).encode()
            if kwargs.get("method") == "POST" and "uploads" in url:
                return 200, {}, b'{"OK":1,"upload_id":"uid-1"}'
            if kwargs.get("method") == "PUT":
                return 500, {}, b"boom"
            return 200, {}, b'{"OK":1}'

        with mock.patch.object(bili_upload, "_http", side_effect=always_500):
            with mock.patch.object(bili_upload.time, "sleep"):
                with self.assertRaises(BiliError) as ctx:
                    bili_upload.Uploader(COOKIE).upload(self.path, limit=1)
        self.assertIn("分片 1/3 上传失败", str(ctx.exception))

    def test_preupload_missing_fields_raises(self):
        with mock.patch.object(bili_upload, "_http", return_value=(200, {}, b'{"OK":1}')):
            with self.assertRaises(BiliError):
                bili_upload.Uploader(COOKIE).upload(self.path)


class SubmitTest(unittest.TestCase):
    def test_url_and_body_carry_csrf(self):
        with mock.patch.object(bili_upload, "_json_call", return_value={"code": 0, "data": {}}) as call:
            bili_upload.Uploader(COOKIE).submit({"title": "T", "tid": 160})
        url, kwargs = call.call_args.args[0], call.call_args.kwargs
        self.assertTrue(url.startswith(bili_upload.SUBMIT_URL + "?"))
        self.assertIn("csrf=csrf123", url)
        self.assertIn("t=", url)
        self.assertEqual(kwargs["method"], "POST")
        self.assertEqual(kwargs["payload"]["csrf"], "csrf123")
        self.assertEqual(kwargs["payload"]["title"], "T")

    def test_missing_csrf_raises(self):
        uploader = bili_upload.Uploader("SESSDATA=abc", csrf="")
        uploader.csrf = ""
        with self.assertRaises(BiliError):
            uploader.submit({"title": "T"})


class CliTest(unittest.TestCase):
    def test_global_state_arg_must_precede_subcommand(self):
        with self.assertRaises(SystemExit):
            bili_upload.build_parser().parse_args(["push", "a.mp4", "--state", "s.json"])

    def test_post_defaults_to_reprint(self):
        args = bili_upload.build_parser().parse_args(["post", "--title", "T", "--tid", "160"])
        self.assertEqual(args.copyright, 2)
        self.assertEqual(args.func, bili_upload.cmd_post)

    def test_push_takes_inputs(self):
        args = bili_upload.build_parser().parse_args(["push", "a.mp4", "dir"])
        self.assertEqual(args.inputs, ["a.mp4", "dir"])


if __name__ == "__main__":
    unittest.main()
