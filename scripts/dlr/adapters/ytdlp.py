"""yt-dlp 通用适配器：youtube / kick / chzzk / soop。

这些平台走同一套 yt-dlp 解析流程，差异只在直播页 URL 与请求头。

soop（SOOP，原 AfreecaTV）的会员订阅直播（live API RESULT=-6）需要登录凭据：
可用 `--netrc`（~/.netrc，machine afreecatv）或 SOOP_USERNAME/SOOP_PASSWORD 环境变量，
也可通过 --cookies 传入已登录会话。检测失败时保留真实错误供引擎打印，
避免把「订阅直播需登录」误报成「未开播」。
"""

from __future__ import annotations

import os

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
        # 允许经 ~/.netrc（machine afreecatv）登录，以抓取会员订阅直播
        "netrc": True,
    },
}


def _clean_error(err: str) -> str:
    """去掉 yt-dlp 的 `ERROR: [<extractor>] <id>:` 前缀，只留可读原因。"""
    text = err.strip()
    if text.startswith("ERROR:"):
        text = text[len("ERROR:"):].lstrip()
    # 去掉 `[extractor:type]` 前缀（其内部可能含冒号，如 `[soop:live]`）
    if text.startswith("["):
        end = text.find("]")
        if end != -1:
            text = text[end + 1:].lstrip()
    # 去掉 `id:` 前缀，只留原因
    if ":" in text:
        text = text.split(":", 1)[1].lstrip()
    return text


class YTDLPAdapter(BaseAdapter):
    def __init__(
        self,
        platform: str,
        target: str,
        cookies: str | None = None,
        cookie_header: str | None = None,
        quality: str = "best",
    ) -> None:
        if platform not in CONFIG:
            raise ValueError(f"不支持的 yt-dlp 平台：{platform}")
        self.platform = platform
        self.config = CONFIG[platform]
        self.referer = self.config["referer"]
        self.bsf_aac = self.config["bsf_aac"]
        self.last_detect_error: str | None = None
        super().__init__(target, cookies=cookies, cookie_header=cookie_header, quality=quality)

    def _extract_identifier(self) -> str:
        return extract_last_segment(self.target)

    @property
    def live_url(self) -> str:
        return self.config["live_url"](self.target)

    def _login_args(self) -> list[str]:
        """soop 订阅直播所需的登录凭据：优先环境变量，其次 netrc。"""
        if not self.config.get("netrc"):
            return []
        username = os.environ.get("SOOP_USERNAME")
        password = os.environ.get("SOOP_PASSWORD")
        if username and password:
            return ["--username", username, "--password", password]
        return ["--netrc"]

    def _run(self, cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
        """执行命令，返回 (returncode, stdout, stderr)。"""
        import subprocess

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except (subprocess.TimeoutExpired, OSError) as exc:
            return 1, "", str(exc)
        return result.returncode, result.stdout, result.stderr

    def detect_stream_url(self) -> str | None:
        self.last_detect_error = None
        # 登录态/Cookie 对所有 yt-dlp 平台统一透传，soop 额外附加登录凭据
        login = [*self.cookie_args(), *self._login_args()]
        if self.quality_height:
            h = self.quality_height
            formats = [f"best[height<={h}]", f"best[height<={h}][ext=flv]", *self.config["formats"]]
        else:
            formats = list(self.config["formats"])
        attempts: list[list[str]] = []
        for fmt in formats:
            attempts.append([*login, "-f", fmt])
        # 兜底：impersonate 一次
        attempts.append([*login, "-f", "b[ext=flv]/best", "--impersonate", "chrome"])

        for args in attempts:
            cmd = ["yt-dlp", "--no-warnings", *args, "--get-url", self.live_url]
            rc, out, err = self._run(cmd)
            if rc == 0:
                line = out.strip().splitlines()
                if line:
                    return line[0]
                continue
            # 记录最后一条非空错误（如「subscription only」），供引擎打印
            reason = next((ln for ln in reversed(err.strip().splitlines()) if ln), None)
            if reason:
                self.last_detect_error = _clean_error(reason)
        return None

    def get_nickname(self) -> str | None:
        login = [*self.cookie_args(), *self._login_args()]
        for field in ("channel", "uploader"):
            cmd = [
                "yt-dlp",
                "--flat-playlist",
                "--no-warnings",
                "--skip-download",
                "--print", f"%({field})s",
                *login,
                self.live_url,
            ]
            rc, out, _ = self._run(cmd)
            if rc == 0:
                value = out.strip().splitlines()
                if value and value[0] != "NA":
                    return value[0]
        return None
