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
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from dlr.adapters.base import pick_flv_url, quality_height


def _request_with_retry(
    session,
    url: str,
    *,
    params: dict | None = None,
    impersonate: str = "chrome131",
    timeout: int = 20,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 8.0,
) -> object | None:
    """GET 请求容错封装：网络异常（TLS/超时/连接重置）按指数退避重试。

    返回 Response；重试耗尽仍失败时返回 None，不抛异常（调用方继续判断/循环）。
    curl_cffi 的 SSLError/Timeout/ConnectionError 均继承自 OSError，一并兜住 raw socket 异常。
    """
    from curl_cffi import requests as curl_requests

    for attempt in range(attempts):
        try:
            return session.get(
                url,
                params=params,
                impersonate=impersonate,
                timeout=timeout,
            )
        except (curl_requests.exceptions.RequestException, OSError) as exc:
            if attempt + 1 < attempts:
                delay = min(base_delay * (2 ** attempt), max_delay)
                print(
                    f"[tiktok_extract] 请求失败({type(exc).__name__}) {url}，"
                    f"{delay:g}s 后重试（{attempt + 1}/{attempts}）",
                    file=sys.stderr,
                )
                time.sleep(delay)
    return None


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
    r = _request_with_retry(
        session,
        "https://webcast.tiktok.com/webcast/room/info/",
        params=params,
        impersonate="chrome131",
        timeout=15,
    )
    if r is None:
        return None

    try:
        data = r.json()
    except Exception:
        return None

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


def _stream_url_from_sigi(text: str) -> str | None:
    """Extract a playable FLV/HLS URL from rendered TikTok SIGI_STATE."""
    match = re.search(r'<script id="SIGI_STATE"[^>]*>(.*?)</script>', text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except (TypeError, ValueError):
        return None

    urls: list[str] = []

    def walk(value: object, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif isinstance(value, str) and value.lower().startswith(("http://", "https://")):
            if "only_audio=1" not in value:
                urls.append(value)
        elif isinstance(value, str) and key in {"stream_data", "streamData"}:
            # Recent pages serialize pull_data.stream_data as JSON.
            try:
                walk(json.loads(value), key)
            except (TypeError, ValueError):
                pass

    live_room = data.get("LiveRoom", {}).get("liveRoomUserInfo", {}).get("liveRoom", {})
    walk(live_room.get("streamData", {}))
    walk(live_room.get("hevcStreamData", {}))
    return next((url for url in urls if ".flv" in url), None) or (urls[0] if urls else None)


def _wait_for_process_group_exit(pgid: int, timeout: float) -> bool:
    """Wait until a POSIX process group no longer has any live members."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(0.05)


def _terminate_process_group(proc: subprocess.Popen, grace: float = 5) -> None:
    """Terminate and reap a subprocess and every member of its process group."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass

    try:
        proc.communicate(timeout=grace)
    except subprocess.TimeoutExpired:
        pass

    if _wait_for_process_group_exit(proc.pid, grace):
        return

    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass

    try:
        proc.communicate(timeout=grace)
    except subprocess.TimeoutExpired:
        pass

    if not _wait_for_process_group_exit(proc.pid, grace):
        raise subprocess.TimeoutExpired(proc.args, grace)


def _active_chromium_profiles() -> set[str]:
    """Return profile paths currently referenced by local Chromium processes."""
    profiles: set[str] = set()
    for cmdline in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            args = cmdline.read_bytes().split(b"\0")
        except (OSError, PermissionError):
            continue
        for arg in args:
            if arg.startswith(b"--user-data-dir="):
                profiles.add(os.fsdecode(arg.partition(b"=")[2]))
    return profiles


def _remove_stale_chromium_profiles(
    profile_parent: Path, *, max_age: float = 600
) -> None:
    """Remove abandoned profiles without touching active or recent probes."""
    active = _active_chromium_profiles()
    cutoff = time.time() - max_age
    for profile in profile_parent.glob("tiktok-chromium-*"):
        try:
            if profile.stat().st_mtime > cutoff or str(profile) in active:
                continue
        except OSError:
            continue
        shutil.rmtree(profile, ignore_errors=True)


def _browser_is_snap(browser: str) -> bool:
    """识别 Snap 可执行文件及 Ubuntu 的 chromium-browser Snap 跳转脚本。"""
    browser_path = Path(browser)
    if browser_path.parts[:3] == ("/", "snap", "bin"):
        return True
    try:
        return "/snap/bin/chromium" in browser_path.read_text(
            encoding="utf-8", errors="ignore"
        )[:4096]
    except (OSError, UnicodeError):
        return False


def _find_headless_browser() -> str | None:
    """优先使用非 Snap 浏览器，避免 Snap/AppArmor 审计噪声。"""
    candidates = [
        shutil.which(name)
        for name in (
            "google-chrome-stable",
            "google-chrome",
            "chromium",
            "chromium-browser",
        )
    ]
    browsers = list(dict.fromkeys(path for path in candidates if path))
    return next((path for path in browsers if not _browser_is_snap(path)), None) or (
        browsers[0] if browsers else None
    )


def _chromium_profile_parent(browser: str) -> str | None:
    """Return a profile parent visible from both host and browser sandbox."""
    if not _browser_is_snap(browser):
        return None

    # A snap's private /tmp is mounted at /tmp/snap-private-tmp on the host.
    # Profiles created in the host /tmp therefore cannot be removed by cleaning
    # the original path. SNAP_USER_COMMON is shared by the host and the snap.
    profile_parent = (
        Path.home() / "snap" / "chromium" / "common" / "chromium-headless"
    )
    profile_parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _remove_stale_chromium_profiles(profile_parent)
    return str(profile_parent)


def _get_stream_url_with_browser(username: str, timeout: int = 35) -> str | None:
    """Resolve SlardarWAF pages through installed headless Chromium."""
    browser = _find_headless_browser()
    if not browser:
        return None
    try:
        profile_parent = _chromium_profile_parent(browser)
        with tempfile.TemporaryDirectory(
            prefix="tiktok-chromium-", dir=profile_parent
        ) as profile:
            proc = subprocess.Popen(
                [browser, "--headless=new", "--no-sandbox", "--disable-gpu",
                 "--disable-vulkan",
                 "--disable-features=Vulkan,VulkanFromANGLE,DefaultANGLEVulkan",
                 "--use-gl=disabled", "--disable-software-rasterizer",
                 "--disable-gpu-compositing",
                 "--disable-dev-shm-usage", f"--user-data-dir={profile}",
                 "--virtual-time-budget=15000", "--dump-dom",
                 f"https://www.tiktok.com/@{username}/live"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                stdout, _ = proc.communicate(timeout=timeout)
            finally:
                # Chromium forks renderer/crashpad processes. Always reap the
                # whole group before TemporaryDirectory removes the profile,
                # including successful, exceptional and interrupted probes.
                _terminate_process_group(proc)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"[tiktok_extract] 浏览器兜底失败：{exc}", file=sys.stderr)
        return None
    stream_url = _stream_url_from_sigi(stdout or "")
    if stream_url:
        print("[tiktok_extract] 浏览器渲染通过 WAF，已从页面取得 FLV", file=sys.stderr)
    return stream_url


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
    _request_with_retry(session, "https://www.tiktok.com", attempts=1)
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
        r = _request_with_retry(
            session,
            f"https://www.tiktok.com/@{username}/live",
            impersonate="chrome131",
            timeout=20,
            attempts=1,
        )
        if r is None:
            if attempt + 1 < attempts:
                time.sleep(min(1.0 * (2 ** attempt), 8.0))
            continue
        text = r.text

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
            time.sleep(min(1.0 * (2 ** attempt), 8.0))
    return None


def get_stream_url(
    username: str,
    quality: str = "best",
    *,
    try_ytdlp: bool = True,
    allow_browser: bool = True,
) -> str | None:
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
    _request_with_retry(session, "https://www.tiktok.com", attempts=1)

    print(f"[tiktok_extract] 检查 @{username} ...", file=sys.stderr)

    # 独立诊断入口保留 yt-dlp 兜底；适配器已经探测过时可跳过，避免重复子进程。
    if try_ytdlp:
        stream_url = _try_ytdlp_fallback(username, max_height)
        if stream_url:
            return stream_url

    # ---- 步骤2：用 curl_cffi 解析页面 ----
    print("[tiktok_extract] yt-dlp 未返回源，尝试 curl_cffi 检测 ...", file=sys.stderr)

    r = _request_with_retry(session, live_url, impersonate="chrome131", timeout=20)
    if r is None:
        print("[tiktok_extract] 多次重试仍无法访问直播页，本次放弃", file=sys.stderr)
        return None

    if allow_browser and (
        "slardar" in r.text.lower() or "please wait" in r.text.lower()
    ):
        stream_url = _get_stream_url_with_browser(username)
        if stream_url:
            return stream_url

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

    # Some accounts expose streamData in the rendered page while room/info is unavailable.
    if allow_browser:
        stream_url = _get_stream_url_with_browser(username)
        if stream_url:
            return stream_url
    else:
        print(
            "[tiktok_extract] 轻量检测无流，本轮跳过 Chromium 兜底",
            file=sys.stderr,
        )

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
