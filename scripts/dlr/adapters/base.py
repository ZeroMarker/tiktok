"""适配器接口：平台只负责"如何解析直播源/昵称"，其余交给引擎。"""

from __future__ import annotations

import abc
import re
from pathlib import Path

# 项目根目录（scripts/dlr/adapters/base.py -> 项目根）
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def extract_last_segment(raw: str) -> str:
    """从 URL 或标识中提取频道段：去查询串、去斜杠、去 @。

    优先识别 @handle 形式（TikTok/YouTube），其次去掉常见动作后缀再取末段。
    """
    cleaned = re.sub(r"[?#].*$", "", raw.strip()).rstrip("/")
    m = re.search(r"@([^/?#]+)", cleaned)
    if m:
        return m.group(1).lstrip("@")
    cleaned = re.sub(r"/(?:live|streams|videos|about)$", "", cleaned)
    return cleaned.rsplit("/", 1)[-1].lstrip("@")


# 录制画质档位（best 为原画/不设上限）。
QUALITY_CHOICES = ("best", "1080p", "720p", "480p")
QUALITY_HEIGHT: dict[str, int | None] = {
    "best": None,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
}
# 各平台 FLV 拉流清晰度 key → 近似视频高度（ORIGIN 为源流，按 1080 处理）。
FLV_QUALITY_KEYS: tuple[tuple[str, int | None], ...] = (
    ("ORIGIN", 1080),
    ("FULL_HD1", 1080),
    ("HD1", 720),
    ("SD1", 480),
    ("SD2", 360),
)


def normalize_quality(quality: str) -> str:
    """校验画质档位，非法输入抛 ValueError。"""
    q = (quality or "best").strip().lower()
    if q not in QUALITY_HEIGHT:
        raise ValueError(f"不支持的录制画质：{quality}")
    return q


def quality_height(quality: str) -> int | None:
    """画质档位 → 目标视频高度上限；None 表示原画/不设上限。"""
    return QUALITY_HEIGHT.get(normalize_quality(quality))


def pick_flv_url(flv: object, max_height: int | None = None) -> str | None:
    """从 FLV 拉流字典中按目标高度挑选 URL。

    max_height 为 None 时取最高可用清晰度（原画档）；否则返回不超过上限的最高
    可用清晰度；若所有可用清晰度都超过上限，则退回最低可用清晰度，保证可录。
    """
    if not isinstance(flv, dict):
        return None
    candidates: list[tuple[int | None, str]] = []
    for key, height in FLV_QUALITY_KEYS:
        url = flv.get(key)
        if isinstance(url, str) and url:
            candidates.append((height, url))
    if not candidates:
        return None
    for height, url in candidates:
        if max_height is None or height is None or height <= max_height:
            return url
    return candidates[-1][1]


class BaseAdapter(abc.ABC):
    """平台适配器基类。

    子类必须实现 detect_stream_url()；get_nickname() 可选（默认无）。
    子类可设置 referer（ffmpeg 请求头）与 bsf_aac（是否加 aac_adtstoasc 比特流过滤）。
    """

    platform: str = ""
    referer: str = ""
    bsf_aac: bool = False

    def __init__(
        self,
        target: str,
        cookies: str | None = None,
        cookie_header: str | None = None,
        quality: str = "best",
    ) -> None:
        self.target = target.strip()
        self.cookies = cookies
        self.cookie_header = cookie_header
        self.quality = normalize_quality(quality)
        self.quality_height = quality_height(self.quality)
        self.identifier = self._extract_identifier()

    @abc.abstractmethod
    def _extract_identifier(self) -> str:
        """从 target 中解析出稳定频道标识（用于目录命名）。"""

    @abc.abstractmethod
    def detect_stream_url(self) -> str | None:
        """返回一条可用流 URL；未开播或抓取失败返回 None。"""

    def get_nickname(self) -> str | None:
        """尽力获取主播昵称；失败返回 None（不影响录制）。"""
        return None

    # ---- 工具 ----

    def run_capture(self, cmd: list[str], timeout: int = 60) -> str | None:
        """执行命令并取 stdout 第一行；失败返回 None。"""
        import subprocess

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
        except (subprocess.TimeoutExpired, OSError):
            return None
        if result.returncode != 0:
            return None
        line = result.stdout.strip().splitlines()
        return line[0] if line else None

    def cookie_args(self) -> list[str]:
        args: list[str] = []
        if self.cookies:
            args += ["--cookies", self.cookies]
        elif self.cookie_header:
            args += ["--cookie", self.cookie_header]
        return args
