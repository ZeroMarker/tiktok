#!/usr/bin/env python3
"""Bili 推流管理 WebUI（独立实现，标准库 only，不依赖 tiktok 仓库）。

管两个 systemd user unit（互斥，同时最多跑一个）：
  bili-live.service    直播推流：push.sh <TARGET>（TikTok 直播源 -> Bilibili）
  bili-replay.service  文件轮播：replay.sh <输入>... [--encode]（本地 mp4 -> Bilibili）

另可开关 B 站房间（live.py start/stop/update/status）。

直播推流目标是**固定的**一个 TikTok 主播（live.env 的 TARGET，管理页填一次即固定）。
常驻监测线程每 60 秒验一次流：开播自动起推流、关播自动停推流（值守开关 auto.env，
「停止全部推流」/「停播」会关掉值守，避免把用户明确停掉的东西拉回来）。

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
import accounts as bili_accounts  # noqa: E402  多账号档案解析（与 live.py 共用同一份逻辑）

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
# 值守开关：直播推流由管理页启动过才写 AUTO=1，监测线程据此决定是否自动接管
AUTO_ENV = CONFIG_DIR / "auto.env"
SESSION_FILE = PROJECT_ROOT / ".bilibili_session.json"


def session_file() -> Path:
    """推流用的登录态：解析 live.py 的默认账号（多账号后不再固定单一文件）。"""
    return bili_accounts.resolve_session(None, None, "live", SESSION_FILE)
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
TRUE_WORDS = {"1", "true", "yes", "on"}
# 目标开播探测间隔（秒）：与 push.sh 的重试节奏一致，UI 每 10 秒轮询只读快照，
# 不会因此多打 TikTok。
TARGET_POLL_INTERVAL = 60.0
# 连续未开播到第几次才停推流：单次失败可能是网络抖动或 WAF 拦，误停会让停播延迟
OFFLINE_STREAK_TO_STOP = 2
PROBE_TIMEOUT = 120


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
        data = json.loads(session_file().read_text())
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
        session = json.loads(session_file().read_text())
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


def probe_target(target: str, timeout: int = PROBE_TIMEOUT) -> tuple[str, str]:
    """探测目标是否开播，返回 (流地址或空, 诊断文案)。与 push.sh 同链路
    （get_stream.py 四级兜底），但失败不抛错：把原因带给 UI——「未开播」和
    「抓流失败」在排障时是两回事。"""
    try:
        r = run(["python3", str(GET_STREAM_PY), target], timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return "", f"验流超时（>{timeout}s）"
    except OSError as exc:
        return "", f"验流失败：{exc}"
    for line in (r.stdout or "").splitlines():
        line = line.strip()
        if line.lower().startswith(STREAM_SCHEMES):
            return line, "已开播"
    err = (r.stderr or "").strip().splitlines()
    return "", err[-1][-200:] if err else "未开播或所有取流方法失败"


def probe_tiktok(target: str, timeout: int = 150) -> str:
    """切源前先验流：拿不到地址就抛错，调用方保持现状不动。"""
    url = probe_target(target, timeout)[0]
    if not url:
        raise ValueError(f"@{target} 当前未开播或抓不到流（已保持原推流不动）")
    return url


# ---- 固定目标开播监测 ----
# 目标只认 live.env 的 TARGET（管理页填一次即固定，之后每轮自动接管）；
# 监测线程独立于 push.sh 轮询：ffmpeg 在推时不再打 TikTok，省掉重复抓流。
_monitor_lock = threading.Lock()
_monitor_state: dict[str, object] = {
    "target": "",     # 当前固定目标（每轮从 live.env 重读，改目标立即生效）
    "live": None,     # True 开播 / False 未开播 / None 未知
    "detail": "等待首次检测",
    "source": "",     # push=ffmpeg 在推（不额外探测）/ probe=探测结果
    "ts": 0.0,        # 上次检测完成的 monotonic
    "next": 0.0,      # 下次检测的 monotonic
    "wall": 0.0,      # 上次检测完成的墙钟时间（给 UI 显示）
    "streak": 0,      # 连续未开播次数
}


def _record(live: bool | None, detail: str, source: str, streak: int | None = None) -> None:
    with _monitor_lock:
        _monitor_state["live"] = live
        _monitor_state["detail"] = detail
        _monitor_state["source"] = source
        now = time.monotonic()
        _monitor_state["ts"] = now
        _monitor_state["next"] = now + TARGET_POLL_INTERVAL
        _monitor_state["wall"] = time.time()
        if streak is not None:
            _monitor_state["streak"] = streak


def auto_armed() -> bool:
    """值守开关：只有管理页启动过直播推流（或已在值守）才允许监测线程接管。

    「停止全部推流」「停播」会关掉它，之后主播开播也不再自动起流——否则用户
    明确停掉的东西会被后台悄悄拉回来。
    """
    return _read_env(AUTO_ENV, "AUTO").strip().lower() in TRUE_WORDS


def _set_armed(armed: bool) -> None:
    _write_env(AUTO_ENV, [f"AUTO={1 if armed else 0}"])


def target_status() -> dict[str, object]:
    """固定目标的开播状态快照（供 /api/status 展示）。"""
    with _monitor_lock:
        state = dict(_monitor_state)
    now = time.monotonic()
    return {
        "target": state["target"],
        "live": state["live"],
        "detail": state["detail"],
        "source": state["source"],
        "checked": time.strftime("%H:%M:%S", time.localtime(state["wall"])) if state["wall"] else "",
        "age": round(now - state["ts"], 1) if state["ts"] else None,
        "next": max(0, round(state["next"] - now)) if state["next"] else None,
        "streak": state["streak"],
        "armed": auto_armed(),
    }


def _auto_control(action) -> bool:
    """监测线程执行控制动作：拿不到用户操作锁就让路，本轮跳过、下轮再来。"""
    if not CONTROL_LOCK.acquire(blocking=False):
        return False
    try:
        action()
        return True
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"开播监测自动接管失败：{exc}", flush=True)
        return False
    finally:
        CONTROL_LOCK.release()


def _start_live_unit(target: str) -> None:
    """开播自动起推流：先保证房间在播，再拉起直播推流单元（同 set_mode 的路径）。"""
    ensure_room_live()
    _write_env(LIVE_ENV, [f"TARGET={target}"])
    run([*SYSTEMCTL, "reset-failed", LIVE_UNIT], check=False)
    _ctl("enable", LIVE_UNIT)
    _ctl("restart", LIVE_UNIT)


def monitor_cycle() -> None:
    """一轮监测：读固定目标 → 判断在播 → 必要时自动启停推流。可独立测试。"""
    target = _read_env(LIVE_ENV, "TARGET").strip()
    with _monitor_lock:
        # 换人就清零连续失败计数：新目标的第一次失败不该继承旧目标的账
        if _monitor_state["target"] != target:
            _monitor_state["streak"] = 0
        _monitor_state["target"] = target
    if not TARGET_RE.fullmatch(target or ""):
        _record(None, "未设置目标主播（管理页填一次即固定）", "")
        return

    units = _show_many(LIVE_UNIT, REPLAY_UNIT)
    live, replay = units[LIVE_UNIT], units[REPLAY_UNIT]
    if replay["active"] == "active":
        # 两种模式互斥是本 WebUI 的硬约束：轮播单元在跑时不抢，只报状态。
        # 判 active 而不是判 ffmpeg：轮播卡死（ffmpeg 已退）时抢单元会变成双推流。
        _record(None, "文件轮播运行中，暂不接管", "")
        return
    # 一次遍历 /proc 同时回答两个 MainPID，直播与轮播共用（省一次全量扫描）
    pushing = _pushing([live["pid"], replay["pid"]])
    if live["active"] == "active" and pushing.get(live["pid"], False):
        # ffmpeg 有流在推就等于开播，不必再打一次 TikTok
        _record(True, "推流中（ffmpeg 已连上源）", "push", 0)
        return

    stream, detail = probe_target(target)
    if stream:
        _record(True, detail, "probe", 0)
        if live["active"] != "active" and auto_armed():
            if _auto_control(lambda: _start_live_unit(target)):
                _record(True, "开播 → 已自动起推流", "probe", 0)
        return

    with _monitor_lock:
        streak = int(_monitor_state["streak"]) + 1
    _record(False, detail, "probe", streak)
    # 关播自动停推流：单次失败可能是网络抖动，连续两次才动手。
    if streak >= OFFLINE_STREAK_TO_STOP and live["active"] == "active" and auto_armed():
        _auto_control(lambda: _ctl("disable", "--now", LIVE_UNIT))


def monitor_loop(stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            monitor_cycle()
        except Exception as exc:  # noqa: BLE001 — 后台线程不能因未知异常退出
            _record(None, f"检测异常：{exc}", "")
        stop.wait(TARGET_POLL_INTERVAL)


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
    return {"mode": mode, "live": live, "replay": replay, "room": room_status(),
            "target": target_status()}


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
        _set_armed(True)   # 值守：之后开播/关播由监测线程自动接管
        with _monitor_lock:
            _monitor_state["streak"] = 0
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
        _set_armed(False)  # 轮播不接管开播：两种模式互斥是硬约束
    else:
        raise ValueError('mode 只能是 "live" 或 "replay"')
    return status()


@exclusive
def arm_auto(data: dict) -> dict[str, object]:
    """值守开关：只交出/收回「自动接管」权，不立刻改变当前推流状态。"""
    enabled = bool(data.get("enabled", True))
    _set_armed(enabled)
    return {"ok": True, "armed": enabled, "status": status()}


@exclusive
def stop_all() -> dict[str, object]:
    _ctl("disable", "--now", LIVE_UNIT)
    _ctl("disable", "--now", REPLAY_UNIT)
    # 明确停掉的东西不能被后台悄悄拉回来：关值守，主播再开播也不自动起流
    _set_armed(False)
    _record(None, "已停止全部推流，值守关闭", "")
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
        _set_armed(False)  # 停播即这场直播结束，不再自动接管
        _record(None, "已停播，值守关闭", "")
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
            elif self.path == "/api/arm":
                self.send_json(HTTPStatus.OK, arm_auto(data))
            elif self.path == "/api/probe":
                # 手动立刻跑一轮检测（不等 60 秒节奏），结果仍写进同一份快照
                monitor_cycle()
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
    # 开播监测常驻：WebUI 关掉页面不影响值守（systemd 拉起即恢复）
    stop_monitor = threading.Event()
    threading.Thread(target=monitor_loop, args=(stop_monitor,),
                     name="live-monitor", daemon=True).start()
    print(f"Bili Push WebUI: http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop_monitor.set()
        server.server_close()


if __name__ == "__main__":
    main()
