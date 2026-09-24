"""webui — 录制任务管理页面与 API。

模块划分（app.py 为兼容门面，聚合导出以下名字）：

    config.py   路径与环境配置（其他模块运行时读取 config.X，保证可 patch）
    jobs.py     任务目录（state/tasks.json）与 systemd 任务操作
    files.py    录制文件列表、解析与删除
    stats.py    系统负载与概览聚合
    server.py   HTTP Handler、静态资源与入口 main()
"""

from __future__ import annotations

__all__ = ["config", "jobs", "files", "stats", "server"]
