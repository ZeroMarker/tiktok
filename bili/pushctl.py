"""推流控制核心（后端库，标准库 only）：systemd 单元、配置文件、开播、验流、控制锁。

两个进程共用：
  monitord.py  值守守护进程（bili-monitord.service）：开播自动起推流、关播自动停推流
  webui/app.py 管理页（bili-webui.service）：展示状态、执行用户操作

两进程之间不共享内存，只通过这些约定交互：
  - 配置：~/.config/bili/{live,replay,auto,push}.env
  - 控制锁：~/.config/bili/control.lock（flock，用户操作与自动接管互斥）
  - 值守快照：~/.config/bili/monitord.json（只有 monitord 写，webui 只读）
  - 立即检测：webui 向 bili-monitord 发 SIGUSR1
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
import accounts as bili_accounts  # noqa: E402  多账号档案解析（与 live.py 共用同一份逻辑）
import subtitle_config  # noqa: E402

LIVE_PY = PROJECT_ROOT / "live.py"
GET_STREAM_PY = PROJECT_ROOT / "get_stream.py"
CONFIG_DIR = Path.home() / ".config" / "bili"
LIVE_ENV = CONFIG_DIR / "live.env"
REPLAY_ENV = CONFIG_DIR / "replay.env"
# 值守开关：直播推流由管理页启动过才写 AUTO=1，monitord 据此决定是否自动接管
AUTO_ENV = CONFIG_DIR / "auto.env"
PUSH_ENV = CONFIG_DIR / "push.env"
SUBTITLE_ENV = CONFIG_DIR / "subtitle.env"
ALIYUN_ENV = CONFIG_DIR / "aliyun.env"
CONTROL_LOCK_FILE = CONFIG_DIR / "control.lock"
MONITOR_STATE_FILE = CONFIG_DIR / "monitord.json"
SESSION_FILE = PROJECT_ROOT / ".bilibili_session.json"

LIVE_UNIT = "bili-live.service"
REPLAY_UNIT = "bili-replay.service"
MONITOR_UNIT = "bili-monitord.service"
SYSTEMCTL = ["systemctl", "--user"]
TARGET_RE = re.compile(r"[A-Za-z0-9_.]{1,64}")
STREAM_SCHEMES = ("http://", "https://", "rtmp://", "rtmps://")
TRUE_WORDS = {"1", "true", "yes", "on"}
PROBE_TIMEOUT = 120


def session_file() -> Path:
    """推流用的登录态：解析 live.py 的默认账号（多账号后不再固定单一文件）。"""
    return bili_accounts.resolve_session(None, None, "live", SESSION_FILE)


def run(argv: list[str], timeout: int = 20, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=check)


# ---- 控制锁（跨进程）----

class ControlBusy(RuntimeError):
    pass


@contextlib.contextmanager
def control_lock():
    """用户操作与自动接管互斥：非阻塞 flock，拿不到抛 ControlBusy。

    flock 绑定在打开的文件描述上，同进程内的并发请求（各自 open）也一样互斥。
    """
    CONFIG_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(CONTROL_LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ControlBusy("另一项操作正在执行，请完成后重试") from None
        yield
    finally:
        os.close(fd)  # 关闭即释放锁


# ---- systemd 单元 ----

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


def show_many(*units: str) -> dict[str, dict[str, object]]:
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


def show(unit: str) -> dict[str, object]:
    return show_many(unit)[unit]


def pushing(root_pids) -> dict[int, bool | None]:
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


def ctl(*args: str) -> None:
    r = run([*SYSTEMCTL, *args], timeout=45, check=False)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip() or "systemctl 执行失败")


def wait_inactive(unit: str, timeout: int = 35) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if show(unit)["active"] in ("inactive", "failed"):
            return True
        time.sleep(1)
    return False


def restart_unit(unit: str) -> None:
    """意图性重启不受 crash 熔断计数限制：先清 start-limit，否则连续切换直接失败且单元变 failed。"""
    run([*SYSTEMCTL, "reset-failed", unit], check=False)
    ctl("enable", unit)
    ctl("restart", unit)  # 新配置只在新进程生效


# ---- 配置文件 ----

def read_env(path: Path, key: str) -> str:
    try:
        for line in path.read_text().splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def write_env(path: Path, lines: list[str]) -> None:
    write_private(path, "# 由 bili 管理（600，不进 git）\n" + "".join(l + "\n" for l in lines))


def write_private(path: Path, text: str) -> None:
    """原子写入 600 私有文件（mkstemp 默认 600，os.replace 保证读者看不到半截内容）。"""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".bili-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def auto_armed() -> bool:
    """值守开关：只有管理页启动过直播推流（或已在值守）才允许 monitord 接管。

    「停止全部推流」「停播」会关掉它，之后主播开播也不再自动起流——否则用户
    明确停掉的东西会被后台悄悄拉回来。
    """
    return read_env(AUTO_ENV, "AUTO").strip().lower() in TRUE_WORDS


def subtitle_status() -> dict[str, object]:
    error = subtitle_config.dependency_error()
    values = subtitle_config.read_credentials(ALIYUN_ENV)
    if not error and not all(values.get(name) for name in subtitle_config.CREDENTIAL_NAMES):
        error = "请配置阿里云翻译凭据（aliyun.env）"
    return {"enabled": read_env(SUBTITLE_ENV, "SUBTITLES").lower() in TRUE_WORDS,
            "ready": not bool(error), "detail": error, "delay": 5, "backend": "aliyun"}


def arm_epoch() -> str:
    """每次开值守写一个新纪元：monitord 见到纪元变化就清零连续下播计数。"""
    return read_env(AUTO_ENV, "EPOCH")


def set_armed(armed: bool) -> None:
    lines = [f"AUTO={1 if armed else 0}"]
    if armed:
        lines.append(f"EPOCH={time.time_ns()}")
    write_env(AUTO_ENV, lines)


# ---- B 站房间 ----

def sync_push_env() -> None:
    """把最新推流码写入独立的私有配置，不修改用户 shell 配置。"""
    try:
        data = json.loads(session_file().read_text())
        url, code = data["rtmp_addr"], data["rtmp_code"]
        if not all(isinstance(v, str) and v and "\n" not in v for v in (url, code)):
            raise ValueError("推流配置为空或格式不正确")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("读取会话推流码失败，请重新开播") from exc
    write_env(PUSH_ENV, [
        f"export BILIBILI_PUSH_URL={shlex.quote(url)}",
        f"export BILIBILI_PUSH_CODE={shlex.quote(code)}",
    ])


def ensure_room_live() -> bool:
    """推流前保证 B 站房间开着：已开直接返回；关播则用上次分区/标题自动开播并同步推流码。
    无历史记录时抛错。返回是否重新开播并刷新了推流码，调用方据此重启推流单元。"""
    r = run(["python3", str(LIVE_PY), "is-live"], timeout=30, check=False)
    if r.returncode == 0:
        return False
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
    return True


def close_room() -> None:
    r = run(["python3", str(LIVE_PY), "stop"], timeout=60, check=False)
    if r.returncode != 0:
        raise RuntimeError((r.stdout + r.stderr).strip()[-2000:] or "关播失败")


# ---- 验流 ----

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


# ---- 值守快照 ----

def read_monitor_state() -> dict | None:
    """读 monitord 写的快照；文件不存在或损坏返回 None（「未知」不能冒充「未开播」）。"""
    try:
        data = json.loads(MONITOR_STATE_FILE.read_text())
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_monitor_state(state: dict) -> None:
    write_private(MONITOR_STATE_FILE, json.dumps(state, ensure_ascii=False))
