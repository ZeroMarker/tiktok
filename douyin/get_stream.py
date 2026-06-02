"""Get Douyin live stream URL using DouyinLiveRecorder.

Usage:
    python get_stream.py <web_rid|url>           # JSON: {stream_url, nickname, is_live}
    python get_stream.py <web_rid|url> --get-url # Just print best stream URL
    python get_stream.py <web_rid|url> --get-nickname  # Just print nickname
"""

import asyncio
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


def pick_best_url(stream_url_data: dict) -> str | None:
    """Pick the best quality stream URL from the stream_url_data dict."""
    if not isinstance(stream_url_data, dict):
        return str(stream_url_data) if stream_url_data else None

    # Try FLV pull URLs in quality order
    flv = stream_url_data.get("flv_pull_url", {})
    for q in ("ORIGIN", "FULL_HD1", "HD1", "SD1", "SD2"):
        if q in flv and flv[q]:
            return flv[q]

    # Fall back to any FLV
    if flv:
        for v in flv.values():
            if v:
                return v

    # Try HLS
    hls = stream_url_data.get("hls_pull_url", "") or ""
    if hls:
        return hls

    hls_map = stream_url_data.get("hls_pull_url_map", {})
    if hls_map:
        for v in hls_map.values():
            if v:
                return v

    return None


async def get_info(url: str):
    try:
        data = await spider.get_douyin_app_stream_data(url)
    except Exception as e:
        return {"stream_url": None, "nickname": None, "is_live": False, "error": str(e)}

    if not data:
        return {"stream_url": None, "nickname": None, "is_live": False}

    # spider.get_douyin_app_stream_data returns (stream_url_data, nickname, is_live) as a tuple
    if isinstance(data, tuple) and len(data) >= 3:
        stream_url_data, nickname, is_live = data[0], data[1], data[2]
        best_url = pick_best_url(stream_url_data) if isinstance(stream_url_data, dict) else str(stream_url_data or "")
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
        best_url = pick_best_url(su) if isinstance(su, dict) else str(su or "")
        return {"stream_url": best_url, "nickname": nickname, "is_live": bool(is_live)}

    return {"stream_url": str(data), "nickname": None, "is_live": bool(data)}


def main():
    if len(sys.argv) < 2:
        print("Usage: python get_stream.py <web_rid|url> [--get-url|--get-nickname]", file=sys.stderr)
        sys.exit(1)

    raw = sys.argv[1]
    url = normalize_url(raw)
    mode = sys.argv[2] if len(sys.argv) > 2 else "json"

    info = asyncio.run(get_info(url))

    if mode == "--get-url":
        print(info.get("stream_url") or "")
    elif mode == "--get-nickname":
        print(info.get("nickname") or "")
    else:
        print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
