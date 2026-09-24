"""任务目录（state/tasks.json）与 systemd 任务操作。

systemd 临时单元由 `systemd-run --collect` 创建，停止后即被回收，因此：
- 「暂停」把启动参数写入任务目录并标记 paused；
- 「继续」按记录重建同名单元；
- WebUI 启动时按目录作为期望状态恢复缺失且未暂停的任务。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import threading
from pathlib import Path

from webui import config

_CATALOG_LOCK = threading.Lock()


def run(
    command: list[str], check: bool = True, timeout: int = 20
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check, timeout=timeout)


def unit_name(platform: str, target: str) -> str:
    readable = re.sub(r"[^a-z0-9]+", "-", target.lower()).strip("-")[:24] or "channel"
    digest = hashlib.sha256(f"{platform}\0{target}".encode()).hexdigest()[:10]
    return f"livestream-rec-{platform}-{readable}-{digest}.service"


def _parse_int(value: object, default: int = 0) -> int:
    """Parse optional numeric systemd properties without breaking the API."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _ffmpeg_descendant(root_pid: int) -> bool | None:
    """检查录制主进程是否有 ffmpeg 子孙进程（即是否正在写分段）。

    True=直播中（ffmpeg 在跑）, False=等待开播（只有引擎轮询进程）,
    None=无法判断（/proc 不可用或进程已消失）。只读 /proc，不做额外平台探测。
    """
    if root_pid <= 0:
        return None
    try:
        children: dict[int, list[int]] = {}
        cmds: dict[int, bytes] = {}
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            try:
                with open(f"/proc/{pid}/stat", "rb") as fh:
                    stat = fh.read()
                ppid = int(stat.rsplit(b")", 1)[-1].split()[1])
                with open(f"/proc/{pid}/cmdline", "rb") as fh:
                    cmds[pid] = fh.read()
            except (OSError, ValueError, IndexError):
                continue
            children.setdefault(ppid, []).append(pid)
        if root_pid not in cmds and root_pid not in children and all(root_pid not in kids for kids in children.values()):
            return None
        seen = {root_pid}
        stack = list(children.get(root_pid, []))
        while stack:
            pid = stack.pop()
            if pid in seen:
                continue
            seen.add(pid)
            cmd = cmds.get(pid, b"").lower()
            if cmd.split(b"\x00", 1)[0].rsplit(b"/", 1)[-1].strip() == b"ffmpeg":
                return True
            stack.extend(children.get(pid, []))
        return False
    except OSError:
        return None


def _live_status(state: object, pid: int) -> str:
    """systemd 状态 + ffmpeg 子进程 → 主播直播状态。"""
    if state != "active":
        return "offline"
    hit = _ffmpeg_descendant(pid)
    if hit is True:
        return "live"
    if hit is False:
        return "waiting"
    return "unknown"


def _live_units() -> list[str]:
    """当前 systemd 中仍存在的录制单元（暂停后单元被回收，只剩任务目录里的记录）。"""
    result = run(
        [config.SYSTEMCTL, "list-units", "livestream-rec-*.service", "--all", "--no-legend", "--plain"],
        check=False,
    )
    return [line.split(None, 1)[0] for line in result.stdout.splitlines() if line.strip()]


def _load_catalog() -> dict[str, dict[str, object]]:
    """读取任务目录（启动参数 + 暂停标记）。文件损坏时按空目录处理，不影响服务。"""
    try:
        raw = json.loads(config.CATALOG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(unit): spec
        for unit, spec in raw.items()
        if isinstance(spec, dict) and _valid_unit(str(unit))
    }


def _save_catalog(catalog: dict[str, dict[str, object]]) -> None:
    config.STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = config.CATALOG_FILE.with_name(config.CATALOG_FILE.name + ".tmp")
    tmp.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    tmp.replace(config.CATALOG_FILE)


def _spec_from_unit(unit: str) -> dict[str, object] | None:
    """目录里没有记录时（命令行或旧版本创建的单元），从 systemd 反推启动参数。"""
    result = run([config.SYSTEMCTL, "show", unit, "--property=Id,Description,ExecStart"], check=False)
    values = dict(item.split("=", 1) for item in result.stdout.splitlines() if "=" in item)
    match = re.match(r"Live recorder: (\S+) (.+)", values.get("Description", ""))
    if values.get("Id") != unit or not match or match.group(1) not in config.PLATFORMS:
        return None
    argv_match = re.search(r"argv\[\]=([^;]*)", values.get("ExecStart", ""))
    argv = shlex.split(argv_match.group(1)) if argv_match else []
    quality = "best"
    cookie_file = ""
    for index, token in enumerate(argv):
        if token == "--quality" and index + 1 < len(argv):
            quality = argv[index + 1]
        elif token == "--cookies" and index + 1 < len(argv):
            cookie_file = argv[index + 1]
    return {
        "platform": match.group(1),
        "target": argv[2] if len(argv) > 2 else match.group(2),
        "quality": quality if quality in config.QUALITY_CHOICES else "best",
        "cookie_file": cookie_file,
        "paused": False,
    }


def _paused_jobs(live: set[str]) -> list[dict[str, object]]:
    """暂停中的任务：单元已被 systemd 回收，仅存在于任务目录。"""
    jobs_list = []
    for unit, spec in _load_catalog().items():
        if not spec.get("paused") or unit in live:
            continue
        platform = str(spec.get("platform", "unknown"))
        target = str(spec.get("target", ""))
        jobs_list.append(
            {
                "unit": unit,
                "state": "paused",
                "substate": "paused",
                "description": f"Live recorder: {platform} {target}",
                "started": "",
                "platform": platform,
                "target": target,
                "pid": 0,
                "memory": 0,
                "restarts": 0,
                "live": "paused",
                "quality": spec.get("quality", "best"),
            }
        )
    return jobs_list


def list_jobs() -> list[dict[str, object]]:
    units = _live_units()
    jobs_list = []
    if units:
        details = run(
            [config.SYSTEMCTL, "show", *units, "--property=Id,ActiveState,SubState,Description,ExecMainStartTimestamp,MainPID,MemoryCurrent,NRestarts"],
            check=False,
        )
        for block in details.stdout.strip().split("\n\n"):
            values = dict(item.split("=", 1) for item in block.splitlines() if "=" in item)
            if not values.get("Id"):
                continue
            description = values.get("Description", "")
            match = re.match(r"Live recorder: (\S+) (.+)", description)
            state = values.get("ActiveState", "unknown")
            pid = _parse_int(values.get("MainPID"))
            jobs_list.append(
                {
                    "unit": values["Id"],
                    "state": state,
                    "substate": values.get("SubState", "unknown"),
                    "description": description,
                    "started": values.get("ExecMainStartTimestamp", ""),
                    "platform": match.group(1) if match else "unknown",
                    "target": match.group(2) if match else description,
                    "pid": pid,
                    "memory": _parse_int(values.get("MemoryCurrent")),
                    "restarts": _parse_int(values.get("NRestarts")),
                    "live": _live_status(state, pid),
                }
            )
    jobs_list.extend(_paused_jobs(set(units)))
    return jobs_list


def _validate_spec(spec: dict[str, object]) -> None:
    platform = str(spec.get("platform", "")).lower()
    target = str(spec.get("target", "")).strip()
    if platform not in config.PLATFORMS:
        raise ValueError("不支持的平台")
    if not target or len(target) > 500 or "\x00" in target:
        raise ValueError("频道或直播 URL 无效")
    if str(spec.get("quality", "best")).lower() not in config.QUALITY_CHOICES:
        raise ValueError("不支持的录制画质")
    cookie_file = str(spec.get("cookie_file", "")).strip()
    if platform == "douyin" and cookie_file and not Path(cookie_file).expanduser().is_file():
        raise ValueError("Cookie 文件不存在")


def _spawn(spec: dict[str, object]) -> str:
    """按任务参数启动 systemd 临时单元（新建与「继续」共用同一条启动路径）。"""
    platform = str(spec["platform"]).lower()
    target = str(spec["target"]).strip()
    command = ["bash", str(config.PROJECT_ROOT / config.PLATFORMS[platform][0]), target]
    cookie_file = str(spec.get("cookie_file", "")).strip()
    if platform == "douyin" and cookie_file:
        command.extend(["--cookies", str(Path(cookie_file).expanduser().resolve())])
    quality = str(spec.get("quality", "best")).lower()
    if quality != "best":
        command.extend(["--quality", quality])

    unit = unit_name(platform, target)
    description = f"Live recorder: {platform} {target}"[:200]
    argv = [
        config.SYSTEMD_RUN,
        f"--unit={unit.removesuffix('.service')}",
        "--collect",
        "--service-type=exec",
        f"--description={description}",
        f"--working-directory={config.PROJECT_ROOT}",
        f"--setenv=RECORDINGS_DIR={config.RECORDINGS_DIR}",
        # 网络依赖：等网络就绪后再拉起录制
        "--property=After=network-online.target",
        "--property=Wants=network-online.target",
        # 停止语义：先 SIGTERM 主进程（脚本 trap 干净收尾 ffmpeg），超时后 SIGKILL 整个 cgroup
        "--property=KillMode=mixed",
        "--property=TimeoutStopSec=30s",
        # 重启策略
        "--property=Restart=on-failure",
        "--property=RestartSec=10s",
    ]
    # 以非 root 身份运行录制（RECORDER_USER 设置时）
    if config.RECORDER_USER:
        argv += [f"--uid={config.RECORDER_USER}", f"--gid={config.RECORDER_USER}"]
    argv += ["--", *command]
    result = run(argv, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "systemd 启动失败")
    return unit


def restore_jobs() -> tuple[list[str], dict[str, str]]:
    """Restore missing non-paused transient units from the persistent catalog."""
    restored: list[str] = []
    failed: dict[str, str] = {}
    with _CATALOG_LOCK:
        catalog = _load_catalog()
        live = set(_live_units())
        for unit, spec in catalog.items():
            if spec.get("paused") or unit in live:
                continue
            try:
                _validate_spec(spec)
                expected = unit_name(str(spec["platform"]), str(spec["target"]))
                if expected != unit:
                    raise ValueError(f"任务名称与启动参数不匹配（应为 {expected}）")
                started = _spawn(spec)
                if started != unit:
                    raise RuntimeError(f"恢复后任务名称不匹配（得到 {started}）")
                restored.append(unit)
                live.add(unit)
            except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                failed[unit] = str(exc)
    return restored, failed


def start_job(data: dict) -> str:
    spec = {
        "platform": str(data.get("platform", "")).lower(),
        "target": str(data.get("target", "")).strip(),
        "quality": str(data.get("quality", "best")).strip().lower(),
        "cookie_file": str(data.get("cookie_file", "")).strip(),
    }
    _validate_spec(spec)
    # 校验重复：同一平台下相同频道（忽略大小写）不允许重复添加
    normalized = str(spec["target"]).casefold()
    with _CATALOG_LOCK:
        catalog = _load_catalog()
        live = set(_live_units())
        for unit, stored in catalog.items():
            if stored.get("paused") and str(stored.get("platform")) == spec["platform"] \
                    and str(stored.get("target", "")).strip().casefold() == normalized:
                raise ValueError(
                    f"录制任务已存在且处于暂停：{spec['platform']} {stored.get('target')}，"
                    f"请使用「继续」恢复（{unit}）"
                )
        for job in list_jobs():
            if job.get("state") == "paused":
                continue
            if job.get("platform") == spec["platform"] and str(job.get("target", "")).strip().casefold() == normalized:
                raise ValueError(f"录制任务已存在：{spec['platform']} {job.get('target')}，请勿重复添加，如需重跑请直接重启该任务")
        unit = _spawn(spec)
        catalog[unit] = spec
        _save_catalog(catalog)
    return unit


def _valid_unit(unit: str) -> bool:
    return bool(re.fullmatch(r"livestream-rec-[a-z0-9-]+\.service", unit))


def pause_job(unit: str) -> None:
    """暂停任务：停止单元并把启动参数留在任务目录，稍后可「继续」。"""
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    with _CATALOG_LOCK:
        catalog = _load_catalog()
        live = set(_live_units())
        if unit not in live:
            raise ValueError("任务当前未在运行，无需暂停")
        spec = catalog.get(unit) or _spec_from_unit(unit)
        if spec is None:
            raise RuntimeError("无法识别该任务的启动参数，请在服务器上手动停止")
        result = run([config.SYSTEMCTL, "stop", unit], check=False, timeout=config.CONTROL_TIMEOUT)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "暂停任务失败")
        catalog[unit] = {**spec, "paused": True}
        _save_catalog(catalog)


def resume_job(unit: str) -> str:
    """继续任务：按任务目录里保存的参数重新拉起单元。"""
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    with _CATALOG_LOCK:
        catalog = _load_catalog()
        live = set(_live_units())
        spec = catalog.get(unit)
        if spec is None or not spec.get("paused"):
            raise ValueError("该任务不在暂停列表中")
        if unit in live:
            raise RuntimeError("任务已在运行")
        _validate_spec(spec)
        started = _spawn(spec)
        catalog[started] = {**spec, "paused": False}
        _save_catalog(catalog)
    return started


def delete_job(unit: str) -> None:
    """删除任务：停止单元并移除任务目录记录（录制文件不受影响）。"""
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    with _CATALOG_LOCK:
        catalog = _load_catalog()
        live = set(_live_units())
        if unit in live:
            result = run([config.SYSTEMCTL, "stop", unit], check=False, timeout=config.CONTROL_TIMEOUT)
            if result.returncode != 0:
                raise RuntimeError(result.stderr.strip() or "删除前停止任务失败")
        catalog.pop(unit, None)
        _save_catalog(catalog)


def restart_job(unit: str) -> None:
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    result = run([config.SYSTEMCTL, "restart", unit], check=False, timeout=config.CONTROL_TIMEOUT)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "重启任务失败")


def job_logs(unit: str, tail: int = 200) -> str:
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    tail = max(1, min(int(tail), 5000))
    result = run(["journalctl", "-u", unit, "-n", str(tail), "--no-pager", "-o", "short-iso"], check=False)
    return result.stdout[-100_000:]
