#!/usr/bin/env python3
"""Local Web UI for managing livestream recorder systemd units.

兼容门面：实现已拆分为同目录模块（config/jobs/files/stats/server），
本文件保留原有公开名字并作为 systemd 单元的直接执行入口
（``ExecStart=.../webui/app.py``）。测试仍可 ``from webui import app``。
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
    CONTROL_TIMEOUT,
    INDEX_FILE,
    PLATFORMS,
    PROJECT_ROOT,
    QUALITY_CHOICES,
    RECORDER_USER,
    RECORDINGS_DIR,
    STATE_DIR,
    SYSTEMCTL,
    SYSTEMD_RUN,
    WEBUI_DIR,
)
from webui.files import delete_file, list_files, recent_files, resolve_recording
from webui.jobs import (
    _ffmpeg_descendant,
    _load_catalog,
    _live_status,
    _live_units,
    _parse_int,
    _paused_jobs,
    _save_catalog,
    _spawn,
    _spec_from_unit,
    _valid_unit,
    _validate_spec,
    delete_job,
    job_logs,
    list_jobs,
    pause_job,
    restart_job,
    resume_job,
    restore_jobs,
    run,
    start_job,
    unit_name,
)
from webui.server import STATIC_FILES, Handler, main
from webui.stats import overview, system_stats

__all__ = [
    "CATALOG_FILE", "CONTROL_TIMEOUT", "INDEX_FILE", "PLATFORMS", "PROJECT_ROOT",
    "QUALITY_CHOICES", "RECORDER_USER", "RECORDINGS_DIR", "STATE_DIR", "SYSTEMCTL",
    "SYSTEMD_RUN", "WEBUI_DIR", "STATIC_FILES", "Handler", "main",
    "delete_file", "list_files", "recent_files", "resolve_recording",
    "delete_job", "job_logs", "list_jobs", "pause_job", "restart_job", "resume_job",
    "restore_jobs", "run", "start_job", "unit_name", "overview", "system_stats",
    "_ffmpeg_descendant", "_live_status", "_live_units", "_spawn",
    "_valid_unit", "_validate_spec", "_load_catalog", "_save_catalog",
    "_spec_from_unit", "_paused_jobs", "_parse_int",
]

if __name__ == "__main__":
    main()
