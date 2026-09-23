"""TikTok 适配器：多方法兜底检测。

yt-dlp 对 TikTok 有风控误判风险且每轮启动开销大，检测顺序：
    1) 进程内轻量检测（curl_cffi 页面 + webcast API，带 Cookie）——每轮必跑
    2) 连续 miss 到第 3 次（升级轮）才跑一次带 Cookie 的 yt-dlp 主域探测
    3) 同一升级轮允许 Chromium 兜底渲染
"""

from __future__ import annotations

import sys

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
        # 方法1：进程内轻量检测（curl_cffi 页面 + webcast API），Cookie 让登录态
        # 频道首轮即命中；只有它连败到升级轮才动用子进程。
        miss_index = self._lightweight_misses + 1
        allow_browser = miss_index >= self.browser_fallback_every
        stream = get_stream_url(
            self.identifier,
            quality=self.quality,
            try_ytdlp=False,
            allow_browser=allow_browser,
            cookies=self.cookies,
        )
        if stream:
            self._lightweight_misses = 0
            return stream

        # 方法2：升级轮（每 3 次连败一次）才跑 yt-dlp 主域探测，避免每轮
        # 冷启动一个 yt-dlp 进程（曾达 ~425 次/小时）。
        if allow_browser:
            print(
                "[tiktok] 升级轮：yt-dlp 主域兜底探测 ...",
                file=sys.stderr,
                flush=True,
            )
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

        self._lightweight_misses = 0 if allow_browser else miss_index
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
