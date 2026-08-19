#!/usr/bin/env python3
"""
live_check.py — TikTok 直播状态检测备用方案

用途：
  当 yt-dlp --get-url 返回空（直播未开启/抓取失败）时，
  用此脚本做二次确认和直接源地址抓取。

检测流程：
  1. 用 curl_cffi 模拟浏览器访问 /live 页面
  2. 解析 SIGI_STATE 中的 liveRoom status / roomId
  3. 若 status==2 视为直播中，直接调用 webcast API 获取流地址
  4. 输出流 URL（stdout），供 tk.sh 的 ffmpeg 使用

使用方法：
  python3 live_check.py <username>
  成功 → 输出一行流 URL
  失败 → exit 1，stderr 输出错误原因

依赖：
  pip install curl_cffi
"""

import sys
import re
import json
import time

try:
    from curl_cffi import requests
except ImportError:
    print("缺少 curl_cffi：pip install curl_cffi", file=sys.stderr)
    sys.exit(1)


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


def check_live_via_webcast_api(session: requests.Session, room_id: str) -> str | None:
    """直接调用 webcast API 检查直播状态，返回流 URL（如果有）。"""
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
                # 优先 FLV（HD1 高清），其次 rtmp/hls
                flv = stream_url.get("flv_pull_url") or {}
                for key in ("HD1", "FULL_HD1", "SD1", "SD2"):
                    url = flv.get(key)
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


def try_ytdlp_fallback(username: str) -> str | None:
    """兜底：用 yt-dlp 再试一次，带不同参数。"""
    import subprocess

    urls_to_try = [
        f"https://www.tiktok.com/@{username}/live",
        f"https://m.tiktok.com/@{username}/live",
    ]

    for url in urls_to_try:
        for fmt_flag in [
            [],
            ["-f", "b[ext=flv]"],
        ]:
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


def main():
    if len(sys.argv) < 2:
        print(f"用法：{sys.argv[0]} <TikTok 用户名>", file=sys.stderr)
        sys.exit(1)

    username = sys.argv[1]
    live_url = f"https://www.tiktok.com/@{username}/live"

    session = requests.Session()
    session.get("https://www.tiktok.com", impersonate="chrome131")

    print(f"[live_check] 检查 @{username} ...", file=sys.stderr)

    # ---- 步骤1：直接 yt-dlp 再试 ----
    stream_url = try_ytdlp_fallback(username)
    if stream_url:
        print(stream_url)
        return

    # ---- 步骤2：用 curl_cffi 解析页面 ----
    print("[live_check] yt-dlp 未返回源，尝试 curl_cffi 检测 ...", file=sys.stderr)

    r = session.get(live_url, impersonate="chrome131", timeout=20)

    # 方法A：SIGI_STATE 检测
    room_id, status = get_room_id_from_sigi(r.text)
    if status == 2 and room_id:
        print(f"[live_check] SIGI_STATE status=2, roomId={room_id}", file=sys.stderr)
        stream_url = check_live_via_webcast_api(session, room_id)
        if stream_url:
            print(stream_url)
            return

    # 方法B：Universal Data 检测
    ud_room_id = get_room_id_from_universal(r.text)
    if ud_room_id:
        print(
            f"[live_check] universal data roomId={ud_room_id}",
            file=sys.stderr,
        )
        stream_url = check_live_via_webcast_api(session, ud_room_id)
        if stream_url:
            print(stream_url)
            return

    # ---- 步骤3：在页面中搜索 roomId 再试 ----
    all_room_ids = re.findall(r'"roomId":"(\d+)"', r.text)
    for rid in set(all_room_ids):
        if rid and rid != "0":
            print(f"[live_check] 尝试 roomId={rid} ...", file=sys.stderr)
            stream_url = check_live_via_webcast_api(session, rid)
            if stream_url:
                print(stream_url)
                return

    # ---- 步骤4：带--impersonate参数再跑yt-dlp ----
    print("[live_check] 所有 API 检测均未发现直播", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
