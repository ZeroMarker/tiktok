"""适配器注册与加载。"""

from __future__ import annotations

from dlr.adapters.base import BaseAdapter
from dlr.adapters.douyin import DouyinAdapter
from dlr.adapters.tiktok import TikTokAdapter
from dlr.adapters.ytdlp import CONFIG as YTDLP_CONFIG
from dlr.adapters.ytdlp import YTDLPAdapter

__all__ = ["BaseAdapter", "DouyinAdapter", "TikTokAdapter", "YTDLPAdapter", "load_adapter"]


def load_adapter(
    platform: str,
    target: str,
    cookies: str | None = None,
    cookie_header: str | None = None,
) -> BaseAdapter:
    if platform in YTDLP_CONFIG:
        return YTDLPAdapter(platform, target, cookies=cookies, cookie_header=cookie_header)
    if platform == "tiktok":
        return TikTokAdapter(target, cookies=cookies, cookie_header=cookie_header)
    if platform == "douyin":
        return DouyinAdapter(target, cookies=cookies, cookie_header=cookie_header)
    raise ValueError(f"不支持的平台：{platform}")
