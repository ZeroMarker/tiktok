"""Get Douyin live stream URL using DouyinLiveRecorder.

Usage:
    python get_stream.py <web_rid|url>           # JSON: {stream_url, nickname, is_live}
    python get_stream.py <web_rid|url> --get-url # Just print best stream URL
    python get_stream.py <web_rid|url> --get-nickname  # Just print nickname
"""

import argparse
import asyncio
import http.cookiejar
import json
import os
import sys

_dlr_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "DouyinLiveRecorder")
sys.path.insert(0, _dlr_path)

from src import spider


def normalize_url(raw: str) -> str:
    raw = raw.strip().lstrip("@")
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    return f"https://live.douyin.com/{raw}"


# FLV 清晰度 key → 近似视频高度（ORIGIN 为源流，按 1080 处理）。
_FLV_QUALITY_KEYS = (
    ("ORIGIN", 1080),
    ("FULL_HD1", 1080),
    ("HD1", 720),
    ("SD1", 480),
    ("SD2", 360),
)
_QUALITY_HEIGHT = {"best": None, "1080p": 1080, "720p": 720, "480p": 480}


def pick_best_url(stream_url_data: dict, max_height: int | None = None) -> str | None:
    """Pick the best quality stream URL from the stream_url_data dict.

    max_height 为 None 时取最高可用清晰度（原画档）；否则返回不超过上限的最高
    可用清晰度；若所有清晰度都超过上限，则退回最低可用清晰度，保证可录。
    """
    if not isinstance(stream_url_data, dict):
        return str(stream_url_data) if stream_url_data else None

    # Try FLV pull URLs, filtered by quality cap
    flv = stream_url_data.get("flv_pull_url", {})
    candidates: list[tuple[int | None, str]] = []
    for q, height in _FLV_QUALITY_KEYS:
        url = flv.get(q) if isinstance(flv, dict) else None
        if isinstance(url, str) and url:
            candidates.append((height, url))
    for height, url in candidates:
        if max_height is None or height is None or height <= max_height:
            return url

    # Fall back to any FLV (lowest available if all exceeded the cap)
    if flv:
        for v in flv.values():
            if isinstance(v, str) and v:
                return v

    # Try HLS
    hls = stream_url_data.get("hls_pull_url", "") or ""
    if hls:
        return hls

    hls_map = stream_url_data.get("hls_pull_url_map", {})
    if hls_map:
        for v in hls_map.values():
            if isinstance(v, str) and v:
                return v

    return None


def load_cookie_header(cookie_file: str) -> str:
    """Load Douyin cookies from a Netscape-format cookie file."""
    jar = http.cookiejar.MozillaCookieJar()
    try:
        jar.load(cookie_file, ignore_discard=True, ignore_expires=True)
    except (FileNotFoundError, http.cookiejar.LoadError, OSError) as exc:
        raise ValueError(f"无法读取 Cookie 文件 {cookie_file}: {exc}") from exc

    allowed_domains = ("douyin.com", "iesdouyin.com", "amemv.com")
    cookies = [
        f"{cookie.name}={cookie.value}"
        for cookie in jar
        if cookie.domain.lstrip(".").endswith(allowed_domains)
    ]
    if not cookies:
        raise ValueError("Cookie 文件中没有找到抖音域名 Cookie")
    return "; ".join(cookies)


async def get_info(url: str, cookies: str | None = None, max_height: int | None = None):
    try:
        data = await spider.get_douyin_app_stream_data(url, cookies=cookies)
    except Exception as e:
        return {"stream_url": None, "nickname": None, "is_live": False, "error": str(e)}

    if not data:
        return {"stream_url": None, "nickname": None, "is_live": False}

    # spider.get_douyin_app_stream_data returns (stream_url_data, nickname, is_live) as a tuple
    if isinstance(data, tuple) and len(data) >= 3:
        stream_url_data, nickname, is_live = data[0], data[1], data[2]
        best_url = pick_best_url(stream_url_data, max_height) if isinstance(stream_url_data, dict) else str(stream_url_data or "")
        return {
            "stream_url": best_url,
            "nickname": nickname or None,
            "is_live": bool(is_live),
        }

    # Handle dict response
    if isinstance(data, dict):
        nickname = data.get("nickname") or data.get("anchor_name") or None
        is_live = data.get("is_live") or data.get("status") == 2 or data.get("live_status") == 1
        su = data.get("stream_url") or data
        best_url = pick_best_url(su, max_height) if isinstance(su, dict) else str(su or "")
        return {"stream_url": best_url, "nickname": nickname, "is_live": bool(is_live)}

    return {"stream_url": str(data), "nickname": None, "is_live": bool(data)}


def main():
    parser = argparse.ArgumentParser(description="获取抖音直播信息")
    parser.add_argument("target", help="web_rid、抖音号或直播间 URL")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--get-url", action="store_true", help="只输出直播源 URL")
    mode.add_argument("--get-nickname", action="store_true", help="只输出主播昵称")
    cookies = parser.add_mutually_exclusive_group()
    cookies.add_argument("--cookies", metavar="FILE", help="Netscape 格式 Cookie 文件")
    cookies.add_argument("--cookie", metavar="HEADER", help="原始 Cookie 请求头")
    parser.add_argument("--quality", choices=("best", "1080p", "720p", "480p"), default="best", help="录制画质")
    args = parser.parse_args()

    try:
        cookie_header = load_cookie_header(args.cookies) if args.cookies else args.cookie
    except ValueError as exc:
        parser.error(str(exc))

    info = asyncio.run(
        get_info(normalize_url(args.target), cookie_header, _QUALITY_HEIGHT.get(args.quality))
    )

    if args.get_url:
        print(info.get("stream_url") or "")
    elif args.get_nickname:
        print(info.get("nickname") or "")
    else:
        print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
