"""yt-dlp 通用适配器：youtube / kick / chzzk / soop。

这些平台走同一套 yt-dlp 解析流程，差异只在直播页 URL 与请求头。
"""

from __future__ import annotations

from dlr.adapters.base import BaseAdapter, extract_last_segment

# 每平台配置：live_url 构造、referer、是否加 aac_adtstoasc
CONFIG: dict[str, dict] = {
    "youtube": {
        "referer": "https://www.youtube.com/",
        "bsf_aac": False,
        "live_url": lambda t: (
            t
            if t.startswith(("http://", "https://"))
            else f"https://www.youtube.com/@{t}/live"
        ),
        "formats": ["best[ext=mp4]/best", "b[ext=flv]/best"],
    },
    "kick": {
        "referer": "https://kick.com/",
        "bsf_aac": False,
        "live_url": lambda t: f"https://kick.com/{t}",
        "formats": ["best[ext=mp4]/best", "b[ext=flv]/best"],
    },
    "chzzk": {
        "referer": "https://chzzk.naver.com/",
        "bsf_aac": False,
        "live_url": lambda t: f"https://chzzk.naver.com/live/{t}",
        "formats": ["best[ext=mp4]/best", "b[ext=flv]/best"],
    },
    "soop": {
        "referer": "https://play.sooplive.co.kr/",
        "bsf_aac": True,
        "live_url": lambda t: (
            t
            if t.startswith(("http://", "https://"))
            else f"https://play.sooplive.co.kr/{t}"
        ),
        "formats": ["best", "b[ext=flv]/best"],
    },
}


class YTDLPAdapter(BaseAdapter):
    def __init__(
        self,
        platform: str,
        target: str,
        cookies: str | None = None,
        cookie_header: str | None = None,
    ) -> None:
        if platform not in CONFIG:
            raise ValueError(f"不支持的 yt-dlp 平台：{platform}")
        self.platform = platform
        self.config = CONFIG[platform]
        self.referer = self.config["referer"]
        self.bsf_aac = self.config["bsf_aac"]
        super().__init__(target, cookies=cookies, cookie_header=cookie_header)

    def _extract_identifier(self) -> str:
        return extract_last_segment(self.target)

    @property
    def live_url(self) -> str:
        return self.config["live_url"](self.target)

    def detect_stream_url(self) -> str | None:
        for fmt in self.config["formats"]:
            url = self.run_capture(
                [
                    "yt-dlp",
                    "--no-warnings",
                    "-f", fmt,
                    "--get-url",
                    self.live_url,
                ]
            )
            if url:
                return url
        # 兜底：impersonate 一次
        return self.run_capture(
            [
                "yt-dlp",
                "--no-warnings",
                "-f", "b[ext=flv]/best",
                "--impersonate", "chrome",
                "--get-url",
                self.live_url,
            ]
        )

    def get_nickname(self) -> str | None:
        for field in ("channel", "uploader"):
            value = self.run_capture(
                [
                    "yt-dlp",
                    "--flat-playlist",
                    "--no-warnings",
                    "--skip-download",
                    "--print", f"%({field})s",
                    self.live_url,
                ]
            )
            if value and value != "NA":
                return value
        return None
