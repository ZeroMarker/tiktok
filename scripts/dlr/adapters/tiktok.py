"""TikTok 适配器：多方法兜底检测。

yt-dlp 对 TikTok 有风控误判风险，因此按优先级依次尝试：
    1) yt-dlp https 主域（FLV 优先）
    2) yt-dlp + --impersonate chrome
    3) yt-dlp mobile 子域
    4) tk/live_check.py（curl_cffi 直接解析页面 + webcast API）
"""

from __future__ import annotations

from dlr.adapters.base import BaseAdapter, PROJECT_ROOT, extract_last_segment

LIVE_CHECK_PY = PROJECT_ROOT / "tk" / "live_check.py"


class TikTokAdapter(BaseAdapter):
    platform = "tiktok"
    referer = "https://www.tiktok.com/"
    bsf_aac = True

    def _extract_identifier(self) -> str:
        return extract_last_segment(self.target)

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
                        "--get-url",
                        url,
                    ]
                )
                if stream:
                    return stream

        # 方法4：Python (curl_cffi) 直接解析页面
        if LIVE_CHECK_PY.is_file():
            return self.run_capture(
                ["python3", str(LIVE_CHECK_PY), self.identifier]
            )
        return None

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
                    profile,
                ]
            )
            if value and value != "NA":
                return value
        return None
