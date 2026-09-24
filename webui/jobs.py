"""任务目录（state/tasks.json）与录制任务调度。

录制执行已收敛为**单进程**（见 recorder.py）：每个任务是 WebUI 进程内的一个
引擎线程，不再创建 systemd 临时单元。本模块负责：

- 任务目录（期望状态）：启动参数与暂停标记的持久化（重启后据此恢复）；
- 校验与去重、暂停/继续/删除/重启的编排（catalog + Recorder 的一致性）；
- 对外提供与旧 systemctl 聚合同形状的任务状态（前端零改动）。

单元名（livestream-rec-*.service）仅作为稳定任务 ID 沿用：
目录键、日志文件名、API 字段都用它，历史数据零迁移。
"""

from __future__ import annotations

import json
import hashlib
import re
import threading
from pathlib import Path

from webui import config, recorder

_CATALOG_LOCK = threading.Lock()
_recorder = recorder.Recorder()


def unit_name(platform: str, target: str) -> str:
    readable = re.sub(r"[^a-z0-9]+", "-", target.lower()).strip("-")[:24] or "channel"
    digest = hashlib.sha256(f"{platform}\0{target}".encode()).hexdigest()[:10]
    return f"livestream-rec-{platform}-{readable}-{digest}.service"


def _valid_unit(unit: str) -> bool:
    return bool(re.fullmatch(r"livestream-rec-[a-z0-9-]+\.service", unit))


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


def list_jobs() -> list[dict[str, object]]:
    """运行中任务（Recorder 状态）+ 暂停中任务（仅存在于任务目录）。"""
    running = _recorder.status()
    seen = {str(job["unit"]) for job in running}
    paused: list[dict[str, object]] = []
    for unit, spec in _load_catalog().items():
        if not spec.get("paused") or unit in seen:
            continue
        platform = str(spec.get("platform", "unknown"))
        target = str(spec.get("target", ""))
        paused.append(
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
    return running + paused


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
        unit = unit_name(spec["platform"], spec["target"])
        _recorder.start(unit, spec)  # 已在运行时抛 RuntimeError
        catalog[unit] = spec
        _save_catalog(catalog)
    return unit


def pause_job(unit: str, timeout: float = 5.0) -> None:
    """暂停任务：优雅停止引擎线程（ffmpeg 收尾当前分段）并保留启动参数。

    短 join（默认 5s）：线程阻在长网络调用时超时转后台收尾，API 不阻塞
    （旧版同步等待可长达 20s+，前端体验差）。"""
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    with _CATALOG_LOCK:
        catalog = _load_catalog()
        spec = _recorder.get_spec(unit)
        if spec is None:
            raise ValueError("任务当前未在运行，无需暂停")
        _recorder.stop(unit, timeout=timeout)
        catalog[unit] = {**spec, "paused": True}
        _save_catalog(catalog)


def resume_job(unit: str) -> str:
    """继续任务：按任务目录里保存的参数重新拉起引擎线程。"""
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    with _CATALOG_LOCK:
        catalog = _load_catalog()
        spec = catalog.get(unit)
        if spec is None or not spec.get("paused"):
            raise ValueError("该任务不在暂停列表中")
        if _recorder.is_running(unit):
            raise RuntimeError("任务已在运行")
        _validate_spec(spec)
        _recorder.start(unit, spec)
        catalog[unit] = {**spec, "paused": False}
        _save_catalog(catalog)
    return unit


def delete_job(unit: str, timeout: float = 5.0) -> None:
    """删除任务：停止引擎线程并移除任务目录记录（录制文件不受影响）。"""
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    with _CATALOG_LOCK:
        catalog = _load_catalog()
        if _recorder.is_running(unit):
            _recorder.stop(unit, timeout=timeout)
        catalog.pop(unit, None)
        _save_catalog(catalog)


def restart_job(unit: str) -> None:
    """重启运行中的任务（暂停中的任务请用「继续」）。"""
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    if not _recorder.is_running(unit):
        raise RuntimeError("任务未在运行（已暂停的任务请使用「继续」）")
    _recorder.restart(unit)


def job_logs(unit: str, tail: int = 200) -> str:
    """任务引擎日志（recordings/logs/<平台>/engine_<unit>.log）的最后 tail 行。"""
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    tail = max(1, min(int(tail), 5000))
    spec = _recorder.get_spec(unit) or _load_catalog().get(unit)
    platform = str((spec or {}).get("platform", ""))
    if platform not in config.PLATFORMS:
        return ""
    return _recorder.tail_log(config.RECORDINGS_DIR, platform, unit, tail)


def restore_jobs() -> tuple[list[str], dict[str, str]]:
    """启动时按任务目录恢复所有未暂停任务（单进程内拉起引擎线程）。

    单个任务恢复失败只记录，不删除目录记录、不阻塞其他任务与服务启动。
    """
    restored: list[str] = []
    failed: dict[str, str] = {}
    with _CATALOG_LOCK:
        catalog = _load_catalog()
        live = _recorder.running_units()
        for unit, spec in catalog.items():
            if spec.get("paused") or unit in live:
                continue
            try:
                _validate_spec(spec)
                expected = unit_name(str(spec["platform"]), str(spec["target"]))
                if expected != unit:
                    raise ValueError(f"任务名称与启动参数不匹配（应为 {expected}）")
                _recorder.start(unit, spec)
                restored.append(unit)
            except (OSError, ValueError, RuntimeError) as exc:
                failed[unit] = str(exc)
    return restored, failed


def shutdown_recorder(timeout: float = 25.0) -> None:
    """进程退出前并行停止全部引擎（每个 ffmpeg 收尾当前分段）。"""
    _recorder.shutdown(timeout=timeout)
