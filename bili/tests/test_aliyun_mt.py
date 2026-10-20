"""云端翻译响应与失败处理；不访问真实服务。"""
import io
import json
import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import aliyun_mt


class AliyunTranslationTest(unittest.TestCase):
    def call(self, result):
        response = io.BytesIO(json.dumps(result).encode())
        with mock.patch.dict("os.environ", {
            "ALIBABA_CLOUD_ACCESS_KEY_ID": "test-key",
            "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "test-secret",
        }), mock.patch.object(aliyun_mt, "urlopen", return_value=response) as send:
            translated = aliyun_mt.translate("こんにちは")
            request = send.call_args.args[0]
            self.assertEqual(request.full_url, "https://mt.cn-hangzhou.aliyuncs.com/")
            self.assertEqual(send.call_args.kwargs["timeout"], 5)
            return translated

    def test_success_with_numeric_or_string_code(self):
        for code in (200, "200"):
            with self.subTest(code=code):
                self.assertEqual(self.call({"Code": code, "Data": {
                    "Translated": "你好\n欢迎"}}), "你好 欢迎")

    def test_business_error_and_missing_translation(self):
        for result in ({"Code": "400"}, {"Code": "200"},
                       {"Code": "200", "Data": {"Translated": " "}}):
            with self.subTest(result=result), self.assertRaises(RuntimeError):
                self.call(result)

    def test_missing_credentials_does_not_send_request(self):
        with mock.patch.dict("os.environ", {}, clear=True), \
                mock.patch.object(aliyun_mt.subtitle_config, "read_credentials", return_value={}), \
                mock.patch.object(aliyun_mt, "urlopen") as send:
            with self.assertRaises(ValueError):
                aliyun_mt.translate("こんにちは")
            send.assert_not_called()

    def test_http_error_hides_response_body(self):
        error = HTTPError("https://example.invalid", 403, "forbidden", {},
                          io.BytesIO(b"sensitive request data"))
        with mock.patch.object(aliyun_mt, "credentials", return_value=("key", "secret")), \
                mock.patch.object(aliyun_mt, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "^阿里云翻译 HTTP 403$"):
                aliyun_mt.translate("こんにちは")


if __name__ == "__main__":
    unittest.main()
