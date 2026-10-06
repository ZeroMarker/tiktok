"""TikTok 适配器：多方法兜底检测。

yt-dlp 对 TikTok 有风控误判风险且每轮启动开销大，检测顺序：
    1) 进程内轻量检测（curl_cffi 页面 + webcast API，带 Cookie）——每轮必跑
    2) 首轮及之后每 3 次连续 miss 的升级轮允许 Chromium 兜底渲染
    3) 升级轮仍未取流且未确认离线时跑带 Cookie 的 yt-dlp 主域探测
"""

from __future__ import annotations

import subprocess
import sys

from dlr.adapters.base import BaseAdapter, extract_last_segment
from dlr.adapters.tiktok_extract import get_nickname as extract_nickname
from dlr.adapters.tiktok_extract import DetectionDiagnostics, get_stream_url


class TikTokAdapter(BaseAdapter):
    platform = "tiktok"
    referer = "https://www.tiktok.com/"
    bsf_aac = True
    browser_fallback_every = 3

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._lightweight_misses = 0
        self._detect_round = 0
        self.last_detect_error = None
        self.diagnostic_log = lambda line: print(line, file=sys.stderr, flush=True)

    def run_capture(self, cmd, timeout=60, *, diagnostics=None):
        if diagnostics is None:
            return super().run_capture(cmd, timeout)
        diagnostics.event("ytdlp", "started")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            diagnostics.event("ytdlp", "timeout")
            return None
        except OSError:
            diagnostics.event("ytdlp", "execution_error")
            return None
        lines = result.stdout.strip().splitlines()
        stream = lines[0] if result.returncode == 0 and lines else None
        outcome = "success" if stream else ("process_error" if result.returncode else "empty_output")
        diagnostics.event("ytdlp", outcome, returncode=result.returncode)
        return stream

    def _extract_identifier(self) -> str:
        return extract_last_segment(self.target)

    def _ytdlp_cookie_args(self) -> list[str]:
        """yt-dlp 可用的 Cookie 参数（Netscape 文件形式）。"""
        if self.cookies:
            return ["--cookies", self.cookies]
        return []

    def detect_stream_url(self) -> str | None:
        # 轻量检测每轮先行；首轮立即允许完整兜底，避免新任务等待两轮。
        self.last_detect_error = None
        self._detect_round += 1
        diag = DetectionDiagnostics(self.diagnostic_log)
        diag.event("round", "started", attempt=self._detect_round)
        miss_index = self._lightweight_misses + 1
        allow_browser = self._detect_round == 1 or miss_index >= self.browser_fallback_every
        stream = get_stream_url(
            self.identifier,
            quality=self.quality,
            try_ytdlp=False,
            allow_browser=allow_browser,
            cookies=self.cookies,
            diagnostics=diag,
        )
        if stream:
            self._lightweight_misses = 0
            diag.event("round", "success")
            return stream

        # 首轮及升级轮才跑 yt-dlp，明确离线时无需继续取流。
        if allow_browser and not diag.confirmed_offline:
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
                ],
                diagnostics=diag,
            )
            if stream:
                self._lightweight_misses = 0
                diag.event("round", "success")
                return stream

        self.last_detect_error = diag.failure_reason
        diag.event("round", "offline" if diag.confirmed_offline else "detection_failed")
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
