#!/usr/bin/env python3
"""Bili 推流管理 WebUI（独立实现，标准库 only，不依赖 tiktok 仓库）。

管两个 systemd user unit（互斥，同时最多跑一个）：
  bili-live.service    直播推流：push.sh <TARGET>（TikTok 直播源 -> Bilibili）
  bili-replay.service  文件轮播：replay.sh <输入>... [--encode]（本地 mp4 -> Bilibili）

另可开关 B 站房间（live.py start/stop/update/status）。

安全：默认只监听 127.0.0.1，无应用层认证；公网发布必须经反代加 Basic Auth。
"""

from __future__ import annotations

import json
from email import policy
from email.parser import BytesParser
import os
import re
import subprocess
import shlex
import tempfile
import threading
import time
from functools import wraps
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEBUI_DIR = Path(__file__).resolve().parent
INDEX_FILE = WEBUI_DIR / "index.html"
MANIFEST_FILE = WEBUI_DIR / "manifest.webmanifest"
SW_FILE = WEBUI_DIR / "sw.js"
ICONS_DIR = WEBUI_DIR / "icons"
LIVE_PY = PROJECT_ROOT / "live.py"
GET_STREAM_PY = PROJECT_ROOT / "get_stream.py"
CONFIG_DIR = Path.home() / ".config" / "bili"
LIVE_ENV = CONFIG_DIR / "live.env"
REPLAY_ENV = CONFIG_DIR / "replay.env"
SESSION_FILE = PROJECT_ROOT / ".bilibili_session.json"
PUSH_ENV = CONFIG_DIR / "push.env"
CONTROL_LOCK = threading.Lock()
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


class ControlBusy(RuntimeError):
    pass


def exclusive(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not CONTROL_LOCK.acquire(blocking=False):
            raise ControlBusy("另一项操作正在执行，请完成后重试")
        try:
            return fn(*args, **kwargs)
        finally:
            CONTROL_LOCK.release()
    return wrapped

LIVE_UNIT = "bili-live.service"
REPLAY_UNIT = "bili-replay.service"
WEBUI_UNIT = "bili-webui.service"
MANAGED_UNITS = {LIVE_UNIT, REPLAY_UNIT}
LOGABLE_UNITS = {LIVE_UNIT, REPLAY_UNIT, WEBUI_UNIT}

TARGET_RE = re.compile(r"[A-Za-z0-9_.]{1,64}")
STREAM_SCHEMES = ("http://", "https://", "rtmp://", "rtmps://")
SYSTEMCTL = ["systemctl", "--user"]


def run(argv: list[str], timeout: int = 20, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=check)
def _unit_props(props: dict[str, str]) -> dict[str, object]:
    try:
        pid = int(props.get("MainPID", "0") or 0)
    except ValueError:
        pid = 0
    return {
        "active": props.get("ActiveState", "unknown"),
        "sub": props.get("SubState", "unknown"),
        "pid": pid,
    }


def _show_many(*units: str) -> dict[str, dict[str, object]]:
    """一次 systemctl show 查多个单元（单元间以空行分隔），比逐个查少一半 fork。"""
    found: dict[str, dict[str, object]] = {}
    r = run([*SYSTEMCTL, "show", *units, "-p", "Id,ActiveState,SubState,MainPID"], check=False)
    if r.returncode == 0:
        for block in re.split(r"\n\s*\n", r.stdout.strip()):
            props = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
            name = props.get("Id")
            if name in units and name not in found:
                found[name] = _unit_props(props)
    for unit in units:  # 输出格式对不上时逐个兜底：宁可多 fork 一次也不给前端错状态
        if unit not in found:
            rr = run([*SYSTEMCTL, "show", unit, "-p", "Id,ActiveState,SubState,MainPID"], check=False)
            props = dict(line.split("=", 1) for line in rr.stdout.splitlines() if "=" in line)
            found[unit] = _unit_props(props)
    return found


def _show(unit: str) -> dict[str, object]:
    return _show_many(unit)[unit]


def _pushing(root_pids) -> dict[int, bool | None]:
    """一次遍历 /proc 构建进程树，同时回答多个 MainPID 是否在推流（有 ffmpeg 子孙）。"""
    roots = list(dict.fromkeys(int(p) for p in root_pids))
    result: dict[int, bool | None] = {pid: False for pid in roots}
    children: dict[int, list[int]] = {}
    comms: dict[int, str] = {}
    try:
        for pid_dir in Path("/proc").iterdir():
            if not pid_dir.name.isdigit():
                continue
            pid = int(pid_dir.name)
            try:
                ppid = int((pid_dir / "stat").read_text().split(")", 1)[1].split()[1])
                comms[pid] = (pid_dir / "comm").read_text().strip()
                children.setdefault(ppid, []).append(pid)
            except (OSError, ValueError, IndexError):
                continue
    except OSError:
        for pid in roots:
            if pid:
                result[pid] = None
        return result

    def has_ffmpeg(root: int) -> bool:
        stack = [root]
        while stack:
            cur = stack.pop()
            if comms.get(cur) == "ffmpeg" and cur != root:
                return True
            stack.extend(children.get(cur, ()))
        return comms.get(root) == "ffmpeg"

    for root in roots:
        if root:
            result[root] = has_ffmpeg(root)
    return result


def _read_env(path: Path, key: str) -> str:
    try:
        for line in path.read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def _write_env(path: Path, lines: list[str]) -> None:
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".bili-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write("# 由 webui 写入（600，不进 git）\n" + "".join(l + "\n" for l in lines))
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


ROOM_TTL = 15.0    # 新鲜期内直接复用缓存：10 秒轮询不再每次起 live.py 打 B 站接口
ROOM_STALE = 300.0  # 旧值可用上限：之内 stale-while-revalidate，超过则同步阻塞刷新
_room_lock = threading.Lock()
_room_event = threading.Event()
_room_state: dict = {"data": None, "ts": 0.0, "refreshing": False}


def _fetch_room() -> dict[str, object]:
    try:
        r = run(["python3", str(LIVE_PY), "status"], timeout=30, check=False)
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


def sync_push_env() -> None:
    """把最新推流码写入独立的私有配置，不修改用户 shell 配置。"""
    try:
        data = json.loads(SESSION_FILE.read_text())
        url, code = data["rtmp_addr"], data["rtmp_code"]
        if not all(isinstance(v, str) and v and "\n" not in v for v in (url, code)):
            raise ValueError("推流配置为空或格式不正确")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("读取会话推流码失败，请重新开播") from exc
    _write_env(PUSH_ENV, [
        f"export BILIBILI_PUSH_URL={shlex.quote(url)}",
        f"export BILIBILI_PUSH_CODE={shlex.quote(code)}",
    ])


def ensure_room_live() -> None:
    """切源前保证 B 站房间开着：已开直接返回；关播则用上次分区/标题自动开播并同步推流码。
    无历史记录时抛错，提示用户去房间卡手动开播。调用方在重启推流单元之前调用，新码即刻生效。"""
    r = run(["python3", str(LIVE_PY), "is-live"], timeout=30, check=False)
    if r.returncode == 0:
        return
    try:
        session = json.loads(SESSION_FILE.read_text())
        area, title = int(session.get("area_id", 0)), str(session.get("title", "")).strip()
    except (OSError, ValueError, TypeError) as exc:
        raise RuntimeError(f"读取上次开播记录失败: {exc}") from exc
    if not area or not title:
        raise ValueError("B 站房间未开播，且没有上次开播记录：请先在房间卡填分区 ID 和标题，点开播")
    r = run(["python3", str(LIVE_PY), "start", "--area", str(area), "--title", title],
            timeout=90, check=False)
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr).strip()[-2000:] or "关播状态下自动开播失败")
    sync_push_env()
    invalidate_room()


def _ctl(*args: str) -> None:
    r = run([*SYSTEMCTL, *args], timeout=45, check=False)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or "systemctl 执行失败")


def _wait_inactive(unit: str, timeout: int = 35) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _show(unit)["active"] in ("inactive", "failed"):
            return True
        time.sleep(1)
    return False
def probe_tiktok(target: str, timeout: int = 150) -> str:
    """切源前先验流：与 push.sh 同链路（get_stream.py 四级兜底）。
    拿不到地址就抛错，调用方保持现状不动。"""
    try:
        r = run(["python3", str(GET_STREAM_PY), target], timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"@{target} 验流超时（已保持原推流不动）") from exc
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line.lower().startswith(STREAM_SCHEMES):
            return line
    raise ValueError(f"@{target} 当前未开播或抓不到流（已保持原推流不动）")




def status() -> dict[str, object]:
    units = _show_many(LIVE_UNIT, REPLAY_UNIT)
    live, replay = units[LIVE_UNIT], units[REPLAY_UNIT]
    pushing = _pushing([live["pid"], replay["pid"]])  # 只扫一次 /proc，两个单元共用进程树
    live["pushing"] = pushing.get(live["pid"], False)
    replay["pushing"] = pushing.get(replay["pid"], False)
    live["target"] = _read_env(LIVE_ENV, "TARGET")
    replay["args"] = _read_env(REPLAY_ENV, "REPLAY_ARGS")
    if live["active"] == "active" and replay["active"] == "active":
        mode = "conflict"
    elif live["active"] == "active":
        mode = "live"
    elif replay["active"] == "active":
        mode = "replay"
    else:
        mode = "idle"
    return {"mode": mode, "live": live, "replay": replay, "room": room_status()}


@exclusive
def set_mode(data: dict) -> dict[str, object]:
    mode = str(data.get("mode", ""))
    if mode == "live":
        target = str(data.get("target", "")).strip()
        if not TARGET_RE.fullmatch(target):
            raise ValueError("TARGET 非法（允许字母数字 . _，≤64 字符）")
        if not bool(data.get("force", False)):
            probe_tiktok(target)  # 先拿到串流地址再停旧起新，失败则保持现状
        ensure_room_live()  # 关播时用上次分区/标题自动开播，否则切了也推不上去
        _write_env(LIVE_ENV, [f"TARGET={target}"])
        _ctl("disable", "--now", REPLAY_UNIT)
        if not _wait_inactive(REPLAY_UNIT):
            raise RuntimeError("文件轮播尚未停止，已取消启动直播推流")
        # 意图性重启不受 crash 熔断计数限制：先清 start-limit，否则连续切换直接 400 且单元变 failed
        run([*SYSTEMCTL, "reset-failed", LIVE_UNIT], check=False)
        _ctl("enable", LIVE_UNIT)
        _ctl("restart", LIVE_UNIT)  # 新 TARGET 只在新进程生效
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
        ensure_room_live()  # 关播时用上次分区/标题自动开播，否则切了也推不上去
        args = " ".join(abs_paths) + (" --encode" if encode else "")
        _write_env(REPLAY_ENV, [f"REPLAY_ARGS={args}"])
        _ctl("disable", "--now", LIVE_UNIT)
        if not _wait_inactive(LIVE_UNIT):
            raise RuntimeError("直播推流尚未停止，已取消启动文件轮播")
        # 意图性重启不受 crash 熔断计数限制：先清 start-limit，否则连续切换直接 400 且单元变 failed
        run([*SYSTEMCTL, "reset-failed", REPLAY_UNIT], check=False)
        _ctl("enable", REPLAY_UNIT)
        _ctl("restart", REPLAY_UNIT)  # 新 REPLAY_ARGS 只在新进程生效
    else:
        raise ValueError('mode 只能是 "live" 或 "replay"')
    return status()


@exclusive
def stop_all() -> dict[str, object]:
    _ctl("disable", "--now", LIVE_UNIT)
    _ctl("disable", "--now", REPLAY_UNIT)
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
        r = run(["python3", str(LIVE_PY), "start", "--area", str(area), "--title", title],
                timeout=90, check=False)
        if r.returncode != 0:
            raise RuntimeError((r.stdout + r.stderr).strip()[-2000:] or "开播失败")
        sync_push_env()
        # 推流码已换：运行中的推流进程拿的还是旧码，必须重启才生效
        for unit in (LIVE_UNIT, REPLAY_UNIT):
            if _show(unit)["active"] == "active":
                _ctl("restart", unit)
        return {"ok": True, "output": r.stdout.strip()[-2000:], "status": status()}
    if action == "stop":
        invalidate_room()
        r = run(["python3", str(LIVE_PY), "stop"], timeout=60, check=False)
        if r.returncode != 0:
            raise RuntimeError((r.stdout + r.stderr).strip()[-2000:] or "停播失败")
        _ctl("disable", "--now", LIVE_UNIT)
        _ctl("disable", "--now", REPLAY_UNIT)
        return {"ok": True, "output": r.stdout.strip()[-1000:], "status": status()}
    if action == "update":
        invalidate_room()
        title = str(data.get("title", "")).strip()
        if not title or len(title) > 40 or "\n" in title:
            raise ValueError("title 非空、≤40 字符、禁 emoji/换行")
        r = run(["python3", str(LIVE_PY), "update", "--title", title], timeout=60, check=False)
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
    else:
        raise ValueError("which 只能是 live、replay 或 webui")
    tail = max(1, min(int(tail), 1000))
    r = run(["journalctl", "--user", "-u", unit, "-n", str(tail), "--no-pager", "-o", "short-iso"],
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
                    result = run(["python3", str(LIVE_PY), "cover", "--file", image.name],
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
