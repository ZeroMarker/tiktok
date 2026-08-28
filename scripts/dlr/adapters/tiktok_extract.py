#!/usr/bin/env python3
"""tiktok_extract.py — TikTok 直播流地址解析（兜底取流，供适配器直接调用）.

用途：
  当 yt-dlp --get-url 返回空（直播未开启/抓取失败）时，
  用此模块二次确认直播状态并直接抓取流地址。

检测流程：
  1. 直接重跑一次带 --impersonate 的 yt-dlp（换主/移动子域）
  2. 用 curl_cffi 模拟浏览器访问 /live 页面
  3. 解析 SIGI_STATE / __UNIVERSAL_DATA__ 中的 liveRoom status / roomId
  4. 若 status==2 视为直播中，直接调用 webcast API 获取流地址
  5. 返回一行流 URL（供 dlr 适配器使用）

用法：
  from dlr.adapters.tiktok_extract import get_stream_url
  url = get_stream_url(username)          # str | None

  命令行诊断：
  python3 tiktok_extract.py <username>    成功→输出一行流 URL，失败→exit 1

依赖：
  pip install curl_cffi  （缺失时 get_stream_url 返回 None，不影响主流程）
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dlr.adapters.base import pick_flv_url, quality_height


def get_room_id_from_sigi(text: str) -> tuple[str | None, int]:
    """从 SIGI_STATE 中提取 liveRoom 信息。
    Returns: (room_id, status_code)
    """
    match = re.search(
        r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', text, re.DOTALL
    )
    if not match:
        return None, -1

    sigi = json.loads(match.group(1))
    lr = sigi.get("LiveRoom", {})

    # 检查 liveRoomUserInfo.liveRoom.status
    room_info = lr.get("liveRoomUserInfo", {}).get("liveRoom", {})
    status = room_info.get("status", 0)
    room_id = room_info.get("roomId")

    # 如果 status != 2 或 room_id 为空，也检查 CurrentRoom
    if status != 2 or not room_id:
        cr = sigi.get("CurrentRoom", {})
        if cr:
            cr_id = cr.get("roomId")
            if cr_id:
                room_id = str(cr_id)
                status = 2  # CurrentRoom 有值视为直播中

    return room_id, status


def get_room_id_from_universal(text: str) -> str | None:
    """从 __UNIVERSAL_DATA_FOR_REHYDRATION__ 中提取 roomId。
    这个值可能是用户永久 roomId，不一定是当前直播的 roomId。
    """
    match = re.search(
        r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>'
        r'(.*?)</script>',
        text,
        re.DOTALL,
    )
    if not match:
        return None
    data = json.loads(match.group(1))
    default_scope = data.get("__DEFAULT_SCOPE__", {})

    # 优先从 webcast-sse.user-detail 或 webcast.user-detail 中取
    for key in ("webcast.user-detail", "webcast-sse.user-detail", "webapp.user-detail"):
        ud = default_scope.get(key, {})
        if ud:
            room_id = ud.get("userInfo", {}).get("user", {}).get("roomId", "")
            if room_id:
                return str(room_id)
    return None


def check_live_via_webcast_api(
    session, room_id: str, max_height: int | None = None
) -> str | None:
    """直接调用 webcast API 检查直播状态，返回流 URL（如果有）。

    max_height 为 None 时返回最高可用清晰度（原画档），否则返回不超过上限的清晰度。
    """
    params = {"room_id": room_id, "aid": "1988"}
    try:
        r = session.get(
            "https://webcast.tiktok.com/webcast/room/info/",
            params=params,
            impersonate="chrome131",
            timeout=15,
        )
        data = r.json()
        status_code = data.get("status_code")
        if status_code != 0:
            return None

        room_info = data.get("data", {})
        if room_info.get("status") == 2:
            # 提取流 URL：stream_url 可能是一个包含各清晰度/协议的字典
            stream_url = room_info.get("stream_url") or {}
            if isinstance(stream_url, dict):
                # 优先 FLV 按清晰度挑选，其次 rtmp/hls
                flv = stream_url.get("flv_pull_url") or {}
                url = pick_flv_url(flv, max_height)
                if url:
                    return url
                for key in ("rtmp_pull_url", "hls_pull_url", "liveUrl"):
                    url = stream_url.get(key)
                    if isinstance(url, str) and url.startswith("http"):
                        return url
            elif isinstance(stream_url, str) and stream_url.startswith("http"):
                return stream_url
            # 直接挂在 data 上的 rtmp/hls
            for key in ("rtmp_pull_url", "hls_pull_url", "liveUrl"):
                url = room_info.get(key)
                if isinstance(url, str) and url.startswith("http"):
                    return url
            return None
    except Exception:
        pass
    return None


def _try_ytdlp_fallback(username: str, max_height: int | None = None) -> str | None:
    """兜底：用 yt-dlp 再试一次，带不同参数。"""
    urls_to_try = [
        f"https://www.tiktok.com/@{username}/live",
        f"https://m.tiktok.com/@{username}/live",
    ]
    if max_height:
        fmt_flags = [
            [],
            ["-f", f"b[height<={max_height}][ext=flv]/best[height<={max_height}]/best"],
        ]
    else:
        fmt_flags = [
            [],
            ["-f", "b[ext=flv]"],
        ]

    for url in urls_to_try:
        for fmt_flag in fmt_flags:
            cmd = (
                ["yt-dlp", "--impersonate", "chrome", "--no-cache-dir"]
                + fmt_flag
                + [url, "--get-url"]
            )
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().split("\n")[0]
            except Exception:
                continue
    return None


def _find_nickname(scope: dict) -> str | None:
    """在 __DEFAULT_SCOPE__ 各命名空间里找 userInfo.user.nickname。"""
    for value in scope.values():
        if not isinstance(value, dict):
            continue
        ui = value.get("userInfo") or {}
        if not isinstance(ui, dict):
            continue
        user = ui.get("user") or {}
        if not isinstance(user, dict):
            continue
        nick = user.get("nickname")
        if isinstance(nick, str) and nick.strip():
            return nick.strip()
    return None


def _find_nickname_from_sigi(sigi: dict, username: str) -> str | None:
    """从 SIGI_STATE 取主播显示昵称：优先 liveRoomUserInfo.user（直播页必有），
    其次 UserModule 中 uniqueId 匹配该频道的用户。"""
    lru = (sigi.get("LiveRoom") or {}).get("liveRoomUserInfo") or {}
    user = lru.get("user") or {}
    nick = user.get("nickname")
    if (
        isinstance(nick, str)
        and nick.strip()
        and user.get("uniqueId") == username
    ):
        return nick.strip()
    users = (sigi.get("UserModule") or {}).get("users") or {}
    for user in users.values():
        if not isinstance(user, dict):
            continue
        if user.get("uniqueId") != username:
            continue
        nick = user.get("nickname")
        if isinstance(nick, str) and nick.strip():
            return nick.strip()
    return None


def get_nickname(
    username: str, cookies: str | None = None, attempts: int = 3
) -> str | None:
    """从直播页（/@user/live）解析显示昵称，优先 SIGI_STATE，其次 universal data。

    部分主播的昵称必须是显示名（如 emiri.okazaki → 丘咲エミリ 本人），
    而 yt-dlp 只能拿到 handle 且不稳定；此函数用 curl_cffi + 可选 Cookie
    直接解析页面 JSON。拿不到返回 None。

    注意：profile 页（/@user）被 TikTok WAF 概率性拦截（返回无数据挑战页），
    直播页（/@user/live）通过率高且 SIGI_STATE 含同样的主播信息，故优先抓直播页；
    仍未命中则短间隔重试若干次。
    """
    try:
        from curl_cffi import requests
    except ImportError:
        return None

    session = requests.Session()
    session.get("https://www.tiktok.com", impersonate="chrome131")
    if cookies:
        try:
            with open(cookies, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        session.cookies.set(
                            parts[5], parts[6], domain=parts[0].lstrip("."), path=parts[2]
                        )
        except OSError:
            pass

    for attempt in range(attempts):
        try:
            r = session.get(
                f"https://www.tiktok.com/@{username}/live",
                impersonate="chrome131",
                timeout=20,
            )
            text = r.text
        except Exception:
            if attempt + 1 < attempts:
                time.sleep(1)
            continue

        # 优先 SIGI_STATE：直播页标准结构，含 liveRoomUserInfo.user.nickname
        match = re.search(
            r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', text, re.DOTALL
        )
        if match:
            try:
                sigi = json.loads(match.group(1))
            except ValueError:
                sigi = None
            if sigi:
                nick = _find_nickname_from_sigi(sigi, username)
                if nick:
                    return nick

        # 其次 universal data（与旧实现相同的解析路径）
        match = re.search(
            r'<script[^>]*id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>(.*?)</script>',
            text,
            re.DOTALL,
        )
        if match:
            try:
                data = json.loads(match.group(1))
            except ValueError:
                data = None
            if data:
                scope = data.get("__DEFAULT_SCOPE__", {}) or {}
                nick = _find_nickname(scope)
                if nick:
                    return nick

        if attempt + 1 < attempts:
            time.sleep(1)
    return None


def get_stream_url(username: str, quality: str = "best") -> str | None:
    """兜底取流主入口：成功返回一行流 URL，失败返回 None。

    quality 为原画/1080p/720p/480p，用于限制返回清晰度；默认 best 原画档。
    """
    max_height = quality_height(quality)
    try:
        from curl_cffi import requests
    except ImportError:
        print("缺少 curl_cffi：pip install curl_cffi", file=sys.stderr)
        return None

    live_url = f"https://www.tiktok.com/@{username}/live"

    session = requests.Session()
    session.get("https://www.tiktok.com", impersonate="chrome131")

    print(f"[tiktok_extract] 检查 @{username} ...", file=sys.stderr)

    # ---- 步骤1：直接 yt-dlp 再试 ----
    stream_url = _try_ytdlp_fallback(username, max_height)
    if stream_url:
        return stream_url

    # ---- 步骤2：用 curl_cffi 解析页面 ----
    print("[tiktok_extract] yt-dlp 未返回源，尝试 curl_cffi 检测 ...", file=sys.stderr)

    r = session.get(live_url, impersonate="chrome131", timeout=20)

    # 方法A：SIGI_STATE 检测
    room_id, status = get_room_id_from_sigi(r.text)
    if status == 2 and room_id:
        print(f"[tiktok_extract] SIGI_STATE status=2, roomId={room_id}", file=sys.stderr)
        stream_url = check_live_via_webcast_api(session, room_id, max_height)
        if stream_url:
            return stream_url

    # 方法B：Universal Data 检测
    ud_room_id = get_room_id_from_universal(r.text)
    if ud_room_id:
        print(
            f"[tiktok_extract] universal data roomId={ud_room_id}",
            file=sys.stderr,
        )
        stream_url = check_live_via_webcast_api(session, ud_room_id, max_height)
        if stream_url:
            return stream_url

    # ---- 步骤3：在页面中搜索 roomId 再试 ----
    all_room_ids = re.findall(r'"roomId":"(\d+)"', r.text)
    for rid in set(all_room_ids):
        if rid and rid != "0":
            print(f"[tiktok_extract] 尝试 roomId={rid} ...", file=sys.stderr)
            stream_url = check_live_via_webcast_api(session, rid, max_height)
            if stream_url:
                return stream_url

    print("[tiktok_extract] 所有 API 检测均未发现直播", file=sys.stderr)
    return None


def main() -> int:
    if len(sys.argv) < 2:
        print(f"用法：{sys.argv[0]} <TikTok 用户名>", file=sys.stderr)
        return 1

    username = sys.argv[1]
    url = get_stream_url(username)
    if url:
        print(url)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
