"""TikTok 适配器：多方法兜底检测。

yt-dlp 对 TikTok 有风控误判风险，因此先做轻量检测：
    1) 单次 yt-dlp 主域检测（FLV 优先）
    2) curl_cffi 直接解析页面 + webcast API
    3) 连续 3 次轻量检测失败后，才允许 Chromium 兜底一次
"""

from __future__ import annotations

from dlr.adapters.base import BaseAdapter, extract_last_segment
from dlr.adapters.tiktok_extract import get_nickname as extract_nickname
from dlr.adapters.tiktok_extract import get_stream_url


class TikTokAdapter(BaseAdapter):
    platform = "tiktok"
    referer = "https://www.tiktok.com/"
    bsf_aac = True
    browser_fallback_every = 3

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._lightweight_misses = 0

    def _extract_identifier(self) -> str:
        return extract_last_segment(self.target)

    def _ytdlp_cookie_args(self) -> list[str]:
        """yt-dlp 可用的 Cookie 参数（Netscape 文件形式）。"""
        if self.cookies:
            return ["--cookies", self.cookies]
        return []

    def detect_stream_url(self) -> str | None:
        # 方法1：单次 yt-dlp 主域探测。避免离线时每轮重复启动多个 yt-dlp。
        url = f"https://www.tiktok.com/@{self.identifier}/live"
        if self.quality_height:
            h = self.quality_height
            fmt = f"b[height<={h}][ext=flv]/best[height<={h}]/best"
        else:
            fmt = "b[ext=flv]/best"
        stream = self.run_capture(
            [
                "yt-dlp",
                "--no-warnings",
                "--impersonate", "chrome",
                "-f", fmt,
                *self._ytdlp_cookie_args(),
                "--get-url",
                url,
            ]
        )
        if stream:
            self._lightweight_misses = 0
            return stream

        # 方法2/3：进程内 HTTP/API 检测；每 3 次连续失败才启用一次浏览器。
        allow_browser = self._lightweight_misses + 1 >= self.browser_fallback_every
        stream = get_stream_url(
            self.identifier,
            quality=self.quality,
            try_ytdlp=False,
            allow_browser=allow_browser,
        )
        if stream:
            self._lightweight_misses = 0
            return stream

        self._lightweight_misses = 0 if allow_browser else self._lightweight_misses + 1
        return None

    def get_nickname(self) -> str | None:
        # 优先：curl_cffi + 可选 Cookie 解析显示昵称（更稳定）。
        # 即使显示名恰好等于 handle（昵称=slug）也是合法昵称，直接返回。
        nick = extract_nickname(self.identifier, cookies=self.cookies)
        if nick:
            return nick

        # 兜底：yt-dlp（带 impersonate + Cookie）。
        # 对 TikTok，%(channel)s 才是显示昵称；%(uploader)s 只会返回 handle
        # （对每个账号都恒等于 identifier，无信息量），故只取 channel。
        profile = f"https://www.tiktok.com/@{self.identifier}"
        value = self.run_capture(
            [
                "yt-dlp",
                "--flat-playlist",
                "--no-warnings",
                "--skip-download",
                "--impersonate", "chrome",
                "--print", "%(channel)s",
                *self._ytdlp_cookie_args(),
                profile,
            ]
        )
        if value and value != "NA":
            return value
        return None
