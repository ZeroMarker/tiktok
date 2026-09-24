"""路径与环境配置。

所有设置以本模块属性的形式存在；jobs/files/stats/server 一律通过
``config.X`` 在运行时读取（而非 from-import 值拷贝），这样测试可以
patch 本模块单一位置而作用于全部使用方。
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEBUI_DIR = Path(__file__).resolve().parent
INDEX_FILE = WEBUI_DIR / "index.html"
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", str(PROJECT_ROOT / "recordings"))

PLATFORMS = {
    "tiktok": ("tk/record.sh",),
    "douyin": ("douyin/record.sh",),
    "soop": ("soop/record.sh",),
    "kick": ("kick/record.sh",),
    "youtube": ("youtube/record.sh",),
    "chzzk": ("chzzk/record.sh",),
}
QUALITY_CHOICES = {"best", "1080p", "720p", "480p"}

# 任务目录：systemd 临时单元在停止后会被回收（`--collect`），暂停中的任务因此需要
# 单独持久化启动参数，才能「继续」时按原样重新拉起单元。
# 目录可由 WEBUI_STATE_DIR / STATE_DIRECTORY 覆盖；生产由 systemd 单元的
# ReadWritePaths 放行（见 systemd/livestream-webui.service）。
STATE_DIR = Path(
    os.environ.get("WEBUI_STATE_DIR")
    or os.environ.get("STATE_DIRECTORY")
    or (PROJECT_ROOT / "state")
)
CATALOG_FILE = STATE_DIR / "tasks.json"
