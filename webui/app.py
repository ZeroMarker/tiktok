#!/usr/bin/env python3
"""WebUI 入口（静态资源 + JSON API）与兼容门面。

架构（见 docs/adr/0002-recorderd-split.md）：

- **本文件 / webui/server.py** = WebUI 进程：只做静态资源、``/api/*`` 编解码、
  录制文件与系统概览；任务状态与控制转发给录制控制面（``webui/control.py``）。
- **webui/recorderd.py** = 录制引擎宿主进程：独占任务目录（state/tasks.json）
  并托管全部引擎线程（``webui/recorder.py``）。

因此重启 WebUI 不再打断录制；反之 recorderd 重启会按任务目录恢复未暂停任务。

本文件同时保留原有公开名字作为兼容门面（实现已拆分为同目录模块
config/jobs/files/stats/server/recorder/control/recorderd），测试仍可
``from webui import app``。注意：导入这些名字不会启动任何引擎。
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
    RECORDERD_SOCKET,
    RECORDINGS_DIR,
    STATE_DIR,
    WEBUI_DIR,
)
from webui.control import (
    ControlUnavailable,
    delete_job,
    job_logs,
    list_jobs,
    pause_job,
    restart_job,
    resume_job,
    start_job,
)
from webui.files import delete_file, list_files, recent_files, resolve_recording
from webui.jobs import (
    _load_catalog,
    _save_catalog,
    _valid_unit,
    _validate_spec,
    restore_jobs,
    shutdown_recorder,
    unit_name,
)
from webui.recorder import Recorder, build_engine, engine_log_path
from webui.recorderd import SHUTDOWN_TIMEOUT, UnixHTTPServer, prepare_socket_path
from webui.server import STATIC_FILES, STATIC_PREFIXES, Handler, main, resolve_static_tree
from webui.stats import overview, system_stats

__all__ = [
    "CATALOG_FILE", "INDEX_FILE", "PLATFORMS", "PROJECT_ROOT",
    "QUALITY_CHOICES", "RECORDERD_SOCKET", "RECORDINGS_DIR", "STATE_DIR", "WEBUI_DIR",
    "STATIC_FILES", "STATIC_PREFIXES", "Handler", "main", "resolve_static_tree",
    "delete_file", "list_files", "recent_files", "resolve_recording",
    "ControlUnavailable", "delete_job", "job_logs", "list_jobs", "pause_job",
    "restart_job", "resume_job", "start_job",
    "SHUTDOWN_TIMEOUT", "UnixHTTPServer", "prepare_socket_path",
    "overview", "system_stats", "Recorder", "build_engine", "engine_log_path",
    "_load_catalog", "_save_catalog", "_valid_unit", "_validate_spec",
    "restore_jobs", "shutdown_recorder", "unit_name",
]

if __name__ == "__main__":
    main()
