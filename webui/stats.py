"""系统负载与概览聚合。"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from webui import config, files, jobs


def system_stats() -> dict[str, object]:
    """系统负载与内存概览（尽力而为，读取失败返回空值）。"""
    try:
        load1, load5, load15 = os.getloadavg()
        load = [round(load1, 2), round(load5, 2), round(load15, 2)]
    except (OSError, AttributeError):
        load = []
    mem_total = mem_available = 0
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                key, _, value = line.partition(":")
                if key == "MemTotal":
                    mem_total = int(value.strip().split()[0]) * 1024
                if key == "MemAvailable":
                    mem_available = int(value.strip().split()[0]) * 1024
    except OSError:
        pass
    return {"load": load, "mem_total": mem_total, "mem_available": mem_available}


def overview() -> dict[str, object]:
    root = Path(config.RECORDINGS_DIR)
    usage = shutil.disk_usage(root if root.exists() else config.PROJECT_ROOT)
    job_list = jobs.list_jobs()
    platforms: dict[str, int] = {}
    for job in job_list:
        platforms[job["platform"]] = platforms.get(job["platform"], 0) + 1
    stats = system_stats()
    return {
        "jobs": len(job_list),
        "running": sum(job["state"] == "active" for job in job_list),
        "live": sum(job.get("live") == "live" for job in job_list),
        "waiting": sum(job.get("live") == "waiting" for job in job_list),
        "failed": sum(job["state"] == "failed" for job in job_list),
        "platforms": platforms,
        "disk_total": usage.total,
        "disk_used": usage.used,
        "disk_free": usage.free,
        "disk_percent": round(usage.used / usage.total * 100, 1),
        "files": files.recent_files(),
        "load": stats["load"],
        "mem_total": stats["mem_total"],
        "mem_available": stats["mem_available"],
        "server_time": int(time.time()),
    }
