#!/usr/bin/env python3
"""Bili 推流管理 WebUI（独立实现，标准库 only，不依赖 tiktok 仓库）。

管两个 systemd user unit（互斥，同时最多跑一个）：
  bili-live.service    直播推流：push.sh <TARGET>（TikTok 直播源 -> Bilibili）
  bili-replay.service  文件轮播：replay.sh <输入>... [--encode]（本地 mp4 -> Bilibili）

另可开关 B 站房间（live.py start/stop/update/status）。

本进程只做「展示 + 用户操作」。值守（开播自动起推流、关播自动停推流）是后端
bili-monitord.service（monitord.py）的事：本进程只读它写的快照，「立即检测」
向它发 SIGUSR1。两者共用 pushctl.py，用户操作与自动接管经 flock 控制锁互斥。
重启/杀掉本进程不影响值守。

安全：默认只监听 127.0.0.1，无应用层认证；公网发布必须经反代加 Basic Auth。
"""

from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from functools import wraps
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import pushctl as ctl  # noqa: E402  后端控制核心（与 monitord 共用）
from pushctl import (  # noqa: E402
    LIVE_PY, LIVE_UNIT, MONITOR_UNIT, REPLAY_UNIT, TARGET_RE, ControlBusy,
)

WEBUI_DIR = Path(__file__).resolve().parent
INDEX_FILE = WEBUI_DIR / "index.html"
MANIFEST_FILE = WEBUI_DIR / "manifest.webmanifest"
SW_FILE = WEBUI_DIR / "sw.js"
ICONS_DIR = WEBUI_DIR / "icons"
_STATIC_CACHE: dict[str, tuple[float, bytes]] = {}

# PWA 静态资源：URL 路径 -> (文件, MIME, Cache-Control)。作用域锁死 WEBUI_DIR，防目录穿越。
PWA_STATIC: dict[str, tuple[Path, str, str]] = {
    "/manifest.webmanifest": (MANIFEST_FILE, "application/manifest+json; charset=utf-8", "public, max-age=3600"),
    "/sw.js": (SW_FILE, "application/javascript; charset=utf-8", "no-cache"),
    "/icons/icon-192.png": (ICONS_DIR / "icon-192.png", "image/png", "public, max-age=86400, immutable"),
    "/icons/icon-512.png": (ICONS_DIR / "icon-512.png", "image/png", "public, max-age=86400, immutable"),
    "/icons/icon.svg": (ICONS_DIR / "icon.svg", "image/svg+xml; charset=utf-8", "public, max-age=86400, immutable"),
    "/icons/icon-maskable-512.png": (ICONS_DIR / "icon-maskable-512.png", "image/png", "public, max-age=86400, immutable"),
    "/icons/apple-touch-icon.png": (ICONS_DIR / "apple-touch-icon.png", "image/png", "public, max-age=86400, immutable"),
    "/favicon.ico": (ICONS_DIR / "icon-192.png", "image/png", "public, max-age=86400, immutable"),
}


# 目录型静态资源（Lit 前端源码 + 本地 vendor，无构建链，源码即产物）：前缀 → webui/ 下的目录。
# 只放行下列后缀，目录里的 .py / __pycache__ / *.map 等不会被暴露。
STATIC_PREFIXES: dict[str, tuple[str, str]] = {
    "/frontend/": ("frontend", "no-cache"),
    "/vendor/": ("vendor", "public, max-age=604800"),
}
STATIC_CONTENT_TYPES: dict[str, str] = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
}


def resolve_static_tree(path: str) -> tuple[Path, str, str] | None:
    """把 ``/frontend/…`` ``/vendor/…`` 映射到 webui/ 下的文件（含穿越防护）。"""
    for prefix, (directory, cache_control) in STATIC_PREFIXES.items():
        if not path.startswith(prefix):
            continue
        relative = path[len(prefix):]
        if not relative or relative.endswith("/"):
            return None
        root = (WEBUI_DIR / directory).resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None  # 目录穿越
        content_type = STATIC_CONTENT_TYPES.get(candidate.suffix.lower())
        if content_type is None or not candidate.is_file():
            return None
        return candidate, content_type, cache_control
    return None

def exclusive(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with ctl.control_lock():
            return fn(*args, **kwargs)
    return wrapped

WEBUI_UNIT = "bili-webui.service"
LOGABLE_UNITS = {LIVE_UNIT, REPLAY_UNIT, WEBUI_UNIT, MONITOR_UNIT}


ROOM_TTL = 15.0    # 新鲜期内直接复用缓存：10 秒轮询不再每次起 live.py 打 B 站接口
ROOM_STALE = 300.0  # 旧值可用上限：之内 stale-while-revalidate，超过则同步阻塞刷新
_room_lock = threading.Lock()
_room_event = threading.Event()
_room_state: dict = {"data": None, "ts": 0.0, "refreshing": False}


def _fetch_room() -> dict[str, object]:
    try:
        r = ctl.run(["python3", str(LIVE_PY), "status"], timeout=30, check=False)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return {"ok": False, "text": f"房间状态查询失败: {exc}"}
    return {"ok": r.returncode == 0, "text": (r.stdout + r.stderr).strip()[-2000:]}


def _room_refresh_bg() -> None:
    try:
        data = _fetch_room()
        with _room_lock:
            _room_state["data"] = data
            _room_state["ts"] = time.monotonic()
    finally:
        with _room_lock:
            _room_state["refreshing"] = False
        _room_event.set()


def room_status() -> dict[str, object]:
    with _room_lock:
        data = _room_state["data"]
        age = time.monotonic() - _room_state["ts"]
        if data is not None and age < ROOM_TTL:
            return dict(data)
        if _room_state["refreshing"]:
            if data is not None:
                return dict(data)  # 已有刷新在跑：先给旧值
        elif data is not None and age < ROOM_STALE:
            _room_state["refreshing"] = True
            threading.Thread(target=_room_refresh_bg, daemon=True).start()
            return dict(data)  # stale-while-revalidate：旧值先上屏，后台补新
        else:
            data = _fetch_room()  # 首次或太久没刷：持锁同步取，天然合并非首次并发请求
            _room_state["data"] = data
            _room_state["ts"] = time.monotonic()
            return dict(data)
    _room_event.wait(35)  # 首个结果生成中：等后台线程出结果
    with _room_lock:
        data = _room_state["data"]
    return dict(data) if data else {"ok": False, "text": "房间状态查询中…"}


def invalidate_room() -> None:
    """开播/停播/改标题后强制下次重新查询，操作完立即看到新状态。"""
    with _room_lock:
        _room_state["ts"] = float("-inf")



def probe_tiktok(target: str, timeout: int = 150) -> str:
    """切源前先验流：拿不到地址就抛错，调用方保持现状不动。"""
    url = ctl.probe_target(target, timeout)[0]
    if not url:
        raise ValueError(f"@{target} 当前未开播或抓不到流（已保持原推流不动）")
    return url


# ---- 值守状态（只读 monitord 的快照）----

def target_status() -> dict[str, object]:
    """固定目标的开播状态快照（供 /api/status 展示）。monitord 不在跑时如实标出，
    不拿旧快照冒充当前状态。"""
    state = ctl.read_monitor_state() or {}
    running = ctl.show(MONITOR_UNIT)["active"] == "active"
    now = time.time()
    checked, next_at = float(state.get("checked_at") or 0), float(state.get("next_at") or 0)
    detail = str(state.get("detail") or "等待首次检测")
    if not running:
        detail = f"值守服务 {MONITOR_UNIT} 未运行（上次结果：{detail}）"
    return {
        "target": ctl.read_env(ctl.LIVE_ENV, "TARGET").strip() or str(state.get("target") or ""),
        "live": state.get("live") if running else None,
        "detail": detail,
        "source": state.get("source", ""),
        "checked": time.strftime("%H:%M:%S", time.localtime(checked)) if checked else "",
        "age": round(now - checked, 1) if checked else None,
        "next": max(0, round(next_at - now)) if next_at and running else None,
        "streak": int(state.get("streak") or 0),
        "armed": ctl.auto_armed(),
        "monitor": running,
    }


def request_probe(wait: float = 0.0) -> bool:
    """让 monitord 立即跑一轮（SIGUSR1）；wait>0 时等到快照更新或超时。返回是否等到新结果。"""
    before = float((ctl.read_monitor_state() or {}).get("checked_at") or 0)
    ctl.ctl("kill", "-s", "USR1", "--kill-whom=main", MONITOR_UNIT)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        if float((ctl.read_monitor_state() or {}).get("checked_at") or 0) > before:
            return True
        time.sleep(0.5)
    return False


def _nudge_monitor() -> None:
    """用户改了推流状态后让值守尽快刷新快照；值守没在跑也不影响用户操作本身。"""
    try:
        request_probe()
    except (RuntimeError, OSError, subprocess.SubprocessError):
        pass



def status() -> dict[str, object]:
    units = ctl.show_many(LIVE_UNIT, REPLAY_UNIT)
    live, replay = units[LIVE_UNIT], units[REPLAY_UNIT]
    pushing = ctl.pushing([live["pid"], replay["pid"]])  # 只扫一次 /proc，两个单元共用进程树
    live["pushing"] = pushing.get(live["pid"], False)
    replay["pushing"] = pushing.get(replay["pid"], False)
    live["target"] = ctl.read_env(ctl.LIVE_ENV, "TARGET")
    replay["args"] = ctl.read_env(ctl.REPLAY_ENV, "REPLAY_ARGS")
    if live["active"] == "active" and replay["active"] == "active":
        mode = "conflict"
    elif live["active"] == "active":
        mode = "live"
    elif replay["active"] == "active":
        mode = "replay"
    else:
        mode = "idle"
    return {"mode": mode, "live": live, "replay": replay, "room": room_status(),
            "target": target_status(), "subtitles": ctl.subtitle_status()}


@exclusive
def set_subtitles(data: dict) -> dict[str, object]:
    enabled = data.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError("enabled 必须是布尔值")
    settings = ctl.subtitle_status()
    if enabled and not settings["ready"]:
        raise ValueError(str(settings["detail"]))
    changed = enabled != settings["enabled"]
    running = ctl.show(LIVE_UNIT)["active"] == "active"
    previous = ctl.SUBTITLE_ENV.read_text() if ctl.SUBTITLE_ENV.exists() else None
    if changed:
        ctl.write_env(ctl.SUBTITLE_ENV, [f"SUBTITLES={int(enabled)}"])
        if running:
            try:
                ctl.ctl("restart", LIVE_UNIT)
            except (RuntimeError, OSError, subprocess.TimeoutExpired):
                if previous is None:
                    ctl.SUBTITLE_ENV.unlink(missing_ok=True)
                else:
                    ctl.write_private(ctl.SUBTITLE_ENV, previous)
                try:
                    ctl.ctl("restart", LIVE_UNIT)
                except (RuntimeError, OSError, subprocess.TimeoutExpired):
                    raise RuntimeError("字幕设置已回退，但推流恢复失败，请重启直播推流") from None
                raise RuntimeError("字幕切换失败，已恢复原设置并重启推流") from None
    return {"ok": True, "restarted": changed and running, "subtitles": ctl.subtitle_status()}


@exclusive
def set_mode(data: dict) -> dict[str, object]:
    mode = str(data.get("mode", ""))
    if mode == "live":
        target = str(data.get("target", "")).strip()
        if not TARGET_RE.fullmatch(target):
            raise ValueError("TARGET 非法（允许字母数字 . _，≤64 字符）")
        if not bool(data.get("force", False)):
            probe_tiktok(target)  # 先拿到串流地址再停旧起新，失败则保持现状
        ctl.ensure_room_live()  # 关播时用上次分区/标题自动开播，否则切了也推不上去
        ctl.write_env(ctl.LIVE_ENV, [f"TARGET={target}"])
        ctl.ctl("disable", "--now", REPLAY_UNIT)
        if not ctl.wait_inactive(REPLAY_UNIT):
            raise RuntimeError("文件轮播尚未停止，已取消启动直播推流")
        ctl.restart_unit(LIVE_UNIT)
        ctl.set_armed(True)   # 值守：之后开播/关播由 monitord 自动接管（新纪元清零下播计数）
        _nudge_monitor()
    elif mode == "replay":
        paths = data.get("paths", [])
        if not isinstance(paths, list) or not paths or len(paths) > 32:
            raise ValueError("paths 需为 1~32 个已存在的文件/目录")
        if any(not isinstance(p, str) for p in paths):
            raise ValueError("paths 含非字符串")
        # 粘贴常带首尾引号（中英文皆有）：去引号后再校验，否则绝对路径也会被误报
        cleaned = [p.strip().strip("\"'“”‘’") for p in paths]
        if any(not p for p in cleaned):
            raise ValueError("存在空路径")
        if any(re.search(r"[\s\x00-\x1f]", p) for p in cleaned):
            raise ValueError("路径含空白字符（systemd 会按空白拆散），请改名")
        abs_paths = [str(Path(p).expanduser()) for p in cleaned]
        if any(not p.startswith("/") for p in abs_paths):
            raise ValueError("只接受绝对路径")
        for p in abs_paths:
            pp = Path(p)
            if not pp.exists():
                raise ValueError(f"路径不存在：{p}")
            if pp.is_dir():
                if not list(pp.glob("*.mp4")):
                    raise ValueError(f"目录无 mp4：{p}")
            elif not (pp.is_file() and pp.suffix.lower() == ".mp4"):
                raise ValueError(f"不是 mp4 文件：{p}")
        encode = bool(data.get("encode", False))
        ctl.ensure_room_live()  # 关播时用上次分区/标题自动开播，否则切了也推不上去
        args = " ".join(abs_paths) + (" --encode" if encode else "")
        ctl.write_env(ctl.REPLAY_ENV, [f"REPLAY_ARGS={args}"])
        ctl.ctl("disable", "--now", LIVE_UNIT)
        if not ctl.wait_inactive(LIVE_UNIT):
            raise RuntimeError("直播推流尚未停止，已取消启动文件轮播")
        ctl.restart_unit(REPLAY_UNIT)
        ctl.set_armed(False)  # 轮播不接管开播：两种模式互斥是硬约束
    else:
        raise ValueError('mode 只能是 "live" 或 "replay"')
    return status()


@exclusive
def arm_auto(data: dict) -> dict[str, object]:
    """值守开关：只交出/收回「自动接管」权，不立刻改变当前推流状态。"""
    enabled = bool(data.get("enabled", True))
    ctl.set_armed(enabled)
    return {"ok": True, "armed": enabled, "status": status()}


@exclusive
def stop_all() -> dict[str, object]:
    ctl.ctl("disable", "--now", LIVE_UNIT)
    ctl.ctl("disable", "--now", REPLAY_UNIT)
    # 明确停掉的东西不能被后台悄悄拉回来：关值守，主播再开播也不自动起流
    ctl.set_armed(False)
    _nudge_monitor()
    return status()


@exclusive
def room(data: dict) -> dict[str, object]:
    action = str(data.get("action", ""))
    if action == "start":
        invalidate_room()
        try:
            area = int(data.get("area", 0))
        except (TypeError, ValueError):
            raise ValueError("area 须为数字（live.py areas 查子分区 ID）")
        if area <= 0:
            raise ValueError("area 须为正整数")
        title = str(data.get("title", "")).strip()
        if not title or len(title) > 40 or "\n" in title:
            raise ValueError("title 非空、≤40 字符、禁 emoji/换行")
        r = ctl.run(["python3", str(LIVE_PY), "start", "--area", str(area), "--title", title],
                timeout=90, check=False)
        if r.returncode != 0:
            raise RuntimeError((r.stdout + r.stderr).strip()[-2000:] or "开播失败")
        ctl.sync_push_env()
        # 推流码已换：运行中的推流进程拿的还是旧码，必须重启才生效
        for unit in (LIVE_UNIT, REPLAY_UNIT):
            if ctl.show(unit)["active"] == "active":
                ctl.ctl("restart", unit)
        return {"ok": True, "output": r.stdout.strip()[-2000:], "status": status()}
    if action == "stop":
        invalidate_room()
        r = ctl.run(["python3", str(LIVE_PY), "stop"], timeout=60, check=False)
        if r.returncode != 0:
            raise RuntimeError((r.stdout + r.stderr).strip()[-2000:] or "停播失败")
        ctl.ctl("disable", "--now", LIVE_UNIT)
        ctl.ctl("disable", "--now", REPLAY_UNIT)
        ctl.set_armed(False)  # 停播即这场直播结束，不再自动接管
        _nudge_monitor()
        return {"ok": True, "output": r.stdout.strip()[-1000:], "status": status()}
    if action == "update":
        invalidate_room()
        title = str(data.get("title", "")).strip()
        if not title or len(title) > 40 or "\n" in title:
            raise ValueError("title 非空、≤40 字符、禁 emoji/换行")
        r = ctl.run(["python3", str(LIVE_PY), "update", "--title", title], timeout=60, check=False)
        if r.returncode != 0:
            raise RuntimeError((r.stdout + r.stderr).strip()[-2000:] or "改标题失败")
        return {"ok": True, "output": r.stdout.strip()[-1000:]}
    raise ValueError('action 只能是 "start"、"stop" 或 "update"')


def unit_logs(which: str, tail: int) -> str:
    if which == "live":
        unit = LIVE_UNIT
    elif which == "replay":
        unit = REPLAY_UNIT
    elif which == "webui":
        unit = WEBUI_UNIT
    elif which == "monitor":
        unit = MONITOR_UNIT
    else:
        raise ValueError("which 只能是 live、replay、webui 或 monitor")
    tail = max(1, min(int(tail), 1000))
    r = ctl.run(["journalctl", "--user", "-u", unit, "-n", str(tail), "--no-pager", "-o", "short-iso"],
                check=False)
    return r.stdout[-100_000:]


def _multipart_file(content_type: str, body: bytes) -> tuple[str, bytes]:
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("ascii", "replace") + b"\r\n\r\n" + body
    )
    if not message.is_multipart():
        raise ValueError("封面上传请求格式错误")
    for part in message.iter_parts():
        disposition = part.get("Content-Disposition", "")
        if part.get_param("name", header="Content-Disposition") == "file":
            payload = part.get_payload(decode=True) or b""
            return part.get_filename() or "cover.jpg", payload
    raise ValueError("未找到封面文件")


class Handler(BaseHTTPRequestHandler):
    server_version = "BiliPushWebUI/1.0"

    def send_json(self, code: int, payload: dict | list) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def authenticated(self) -> bool:
        # 认证已移除：仅监听回环地址；公网发布必须经反代加 Basic Auth。
        return True

    def send_file(self, path: Path, mime: str, cache: str, extra: dict[str, str] | None = None) -> None:
        mtime = path.stat().st_mtime  # 静态文件按 mtime 缓存字节，避免每请求读盘
        hit = _STATIC_CACHE.get(str(path))
        if hit is not None and hit[0] == mtime:
            body = hit[1]
        else:
            body = path.read_bytes()
            _STATIC_CACHE[str(path)] = (mtime, body)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path in ("/", "/index.html"):
                self.send_file(INDEX_FILE, "text/html; charset=utf-8", "no-store")
            elif parsed.path in PWA_STATIC:
                path, mime, cache = PWA_STATIC[parsed.path]
                extra = {"Service-Worker-Allowed": "/"} if parsed.path == "/sw.js" else None
                self.send_file(path, mime, cache, extra)
            elif (tree := resolve_static_tree(parsed.path)) is not None:
                self.send_file(*tree)
            elif parsed.path == "/api/health":
                self.send_json(HTTPStatus.OK, {"ok": True})
            elif parsed.path == "/api/status":
                self.send_json(HTTPStatus.OK, status())
            elif parsed.path == "/api/logs":
                q = parse_qs(parsed.query)
                self.send_json(HTTPStatus.OK, {
                    "logs": unit_logs(q.get("which", ["live"])[0],
                                      int(q.get("tail", ["200"])[0] or "200")),
                })
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 10 * 1024 * 1024 + 64 * 1024:
                raise ValueError("请求过大")
            raw = self.rfile.read(length)
            if self.path == "/api/cover":
                filename, content = _multipart_file(self.headers.get("Content-Type", ""), raw)
                print(f"cover upload received file={Path(filename).name!r} bytes={len(content)}", flush=True)
                suffix = Path(filename).suffix.lower()
                if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
                    raise ValueError("封面仅支持 JPG、PNG 或 WEBP")
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as image:
                    image.write(content)
                    image.flush()
                    result = ctl.run(["python3", str(LIVE_PY), "cover", "--file", image.name],
                                 timeout=90, check=False)
                if result.returncode != 0:
                    print(f"cover upload failed: {(result.stdout + result.stderr).strip()[-2000:]}", flush=True)
                    raise RuntimeError((result.stdout + result.stderr).strip()[-2000:] or "设置封面失败")
                print(f"cover upload succeeded file={Path(filename).name!r}", flush=True)
                self.send_json(HTTPStatus.OK, {"ok": True, "output": result.stdout.strip()[-1000:]})
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type and content_type != "application/json":
                raise ValueError("请求必须是 JSON")
            data = json.loads(raw or b"{}")
            if not isinstance(data, dict):
                raise ValueError("请求内容须为 JSON 对象")
            if self.path == "/api/mode":
                self.send_json(HTTPStatus.OK, set_mode(data))
            elif self.path == "/api/stop":
                self.send_json(HTTPStatus.OK, stop_all())
            elif self.path == "/api/arm":
                self.send_json(HTTPStatus.OK, arm_auto(data))
            elif self.path == "/api/subtitles":
                self.send_json(HTTPStatus.OK, set_subtitles(data))
            elif self.path == "/api/probe":
                # 手动立刻跑一轮检测（不等 60 秒节奏）：交给 monitord，等它写出新快照
                request_probe(wait=ctl.PROBE_TIMEOUT + 10)
                self.send_json(HTTPStatus.OK, {"target": target_status(), "status": status()})
            elif self.path == "/api/room":
                self.send_json(HTTPStatus.OK, room(data))
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except ControlBusy as exc:
            self.send_json(HTTPStatus.CONFLICT, {"error": str(exc)})
        except (ValueError, RuntimeError, json.JSONDecodeError,
                OSError, subprocess.TimeoutExpired) as exc:
            if self.path == "/api/cover":
                print(f"cover upload request error: {exc}", flush=True)
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    host = os.environ.get("BILI_WEBUI_HOST", "127.0.0.1")
    port = int(os.environ.get("BILI_WEBUI_PORT", "8767"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Bili Push WebUI: http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
