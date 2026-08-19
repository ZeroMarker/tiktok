"""TikTok 适配器：多方法兜底检测。

yt-dlp 对 TikTok 有风控误判风险，因此按优先级依次尝试：
    1) yt-dlp https 主域（FLV 优先）
    2) yt-dlp + --impersonate chrome
    3) yt-dlp mobile 子域
    4) curl_cffi 直接解析页面 + webcast API（tiktok_extract.get_stream_url）
"""

from __future__ import annotations

from dlr.adapters.base import BaseAdapter, extract_last_segment
from dlr.adapters.tiktok_extract import get_stream_url


class TikTokAdapter(BaseAdapter):
    platform = "tiktok"
    referer = "https://www.tiktok.com/"
    bsf_aac = True

    def _extract_identifier(self) -> str:
        return extract_last_segment(self.target)

    def _ytdlp_cookie_args(self) -> list[str]:
        """yt-dlp 可用的 Cookie 参数（Netscape 文件形式）。"""
        if self.cookies:
            return ["--cookies", self.cookies]
        return []

    def detect_stream_url(self) -> str | None:
        # 方法1/2/3：yt-dlp 变体
        urls = (
            f"https://www.tiktok.com/@{self.identifier}/live",
            f"https://m.tiktok.com/@{self.identifier}/live",
        )
        for url in urls:
            for extra in ([], ["--impersonate", "chrome"]):
                stream = self.run_capture(
                    [
                        "yt-dlp",
                        "--no-warnings",
                        "-f", "b[ext=flv]/best",
                        *extra,
                        *self._ytdlp_cookie_args(),
                        "--get-url",
                        url,
                    ]
                )
                if stream:
                    return stream

        # 方法4：Python (curl_cffi) 直接解析页面 + webcast API
        return get_stream_url(self.identifier)

    def get_nickname(self) -> str | None:
        profile = f"https://www.tiktok.com/@{self.identifier}"
        for field in ("channel", "uploader"):
            value = self.run_capture(
                [
                    "yt-dlp",
                    "--flat-playlist",
                    "--no-warnings",
                    "--skip-download",
                    "--print", f"%({field})s",
                    *self._ytdlp_cookie_args(),
                    profile,
                ]
            )
            if value and value != "NA":
                return value
        return None
