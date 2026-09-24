#!/usr/bin/env python3
"""Local Web UI for managing livestream recorder systemd units.

兼容门面：实现已拆分为同目录模块（config/jobs/files/stats/server/recorder），
本文件保留原有公开名字并作为 systemd 单元的直接执行入口
（``ExecStart=.../webui/app.py``）。测试仍可 ``from webui import app``。

录制执行是单进程模型：所有频道的引擎线程由 recorder 调度（见 recorder.py），
不再按频道创建 systemd 临时单元。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 直接以脚本执行时（systemd ExecStart），本模块不在包上下文中，
# 先把仓库根加入 sys.path 才能 import webui.*。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webui.config import (
    CATALOG_FILE,
    INDEX_FILE,
    PLATFORMS,
    PROJECT_ROOT,
    QUALITY_CHOICES,
    RECORDINGS_DIR,
    STATE_DIR,
    WEBUI_DIR,
)
from webui.files import delete_file, list_files, recent_files, resolve_recording
from webui.jobs import (
    _load_catalog,
    _save_catalog,
    _valid_unit,
    _validate_spec,
    delete_job,
    job_logs,
    list_jobs,
    pause_job,
    restart_job,
    resume_job,
    restore_jobs,
    shutdown_recorder,
    start_job,
    unit_name,
)
from webui.recorder import Recorder, build_engine, engine_log_path
from webui.server import STATIC_FILES, Handler, main
from webui.stats import overview, system_stats

__all__ = [
    "CATALOG_FILE", "INDEX_FILE", "PLATFORMS", "PROJECT_ROOT",
    "QUALITY_CHOICES", "RECORDINGS_DIR", "STATE_DIR", "WEBUI_DIR",
    "STATIC_FILES", "Handler", "main",
    "delete_file", "list_files", "recent_files", "resolve_recording",
    "delete_job", "job_logs", "list_jobs", "pause_job", "restart_job",
    "resume_job", "restore_jobs", "shutdown_recorder", "start_job", "unit_name",
    "overview", "system_stats", "Recorder", "build_engine", "engine_log_path",
    "_load_catalog", "_save_catalog", "_valid_unit", "_validate_spec",
]

if __name__ == "__main__":
    main()
