# ADR 0002：把录制引擎从 WebUI 进程里拆出来（recorderd 控制面）

- 状态：已采纳
- 日期：2026-10-19
- 范围：`webui/`、`systemd/`。前端契约不变（前端零改动）。
- 相关：[ADR 0001](0001-webui-frontend-lit.md)（前端选型）

## 背景

改造前是**单进程模型**：`livestream-webui.service` 一个 Python 进程既：

1. 托管全部录制引擎线程（`webui/recorder.py` → `scripts/dlr/engine.py` → ffmpeg）；
2. 独占写入任务目录 `state/tasks.json`；
3. 提供 WebUI 静态资源与 `/api/*`。

因此**重启 WebUI 就等于停掉全部录制**（SIGTERM → 逐个引擎收尾当前分段 → 重启后再恢复）。
2026-10-19 的一次误操作（`pkill -f webui/app.py` 同时命中了 systemd 托管的服务进程）
造成 41 分钟中断、Caddy 对外 502、45 个任务集体停摆，正是这个耦合的直接后果。
除此之外还有：改一行前端要停录、UI 崩溃/OOM 会带走引擎、二者无法各自设资源与重启策略。

## 决策

把「引擎宿主」拆成独立服务，两个进程各自有 systemd 生命周期：

```
livestream-recorderd.service   webui/recorderd.py
  ├── Recorder（N 个引擎线程 → 各频道 ffmpeg）
  ├── jobs.py：任务目录 state/tasks.json 的**唯一写入者**（期望状态）
  └── 控制面：本地 unix socket（默认 <STATE_DIR>/run/recorderd.sock，0700 目录 / 0600 socket）

livestream-webui.service       webui/app.py
  ├── 静态资源（/、/frontend/、/vendor/、manifest/sw/图标）
  ├── /api/*：任务状态与控制 → control.py 转发给 recorderd；
  │           录制文件（列表/下载/删除）与系统概览 → 本进程的文件系统视图
  └── SIGTERM 直接退出（没有引擎要收尾）
```

要点：

- **控制通道只用 unix socket**，不占端口、不对外可达；`control.py` 用标准库
  （`http.client` + `AF_UNIX`）实现，不引入依赖。
- **任务目录单一写者**：只有 recorderd 读写 `state/tasks.json`。WebUI 不再需要理解目录格式。
- **WebUI 是纯客户端**：`jobs.list_jobs/start_job/pause_job/resume_job/restart_job/delete_job/job_logs`
  在 WebUI 侧全部由 `control.py` 的同名函数承担，因此 `server.py` / `stats.py` 只换了模块名，
  **`/api/*` 的 JSON 形状与状态码语义保持不变，前端零改动**。
- **降级行为**：recorderd 不可达时，`/api/jobs`、`/api/overview`、`/api/logs` 与控制类 POST
  返回 **503**（`{"error": "录制服务不可用（…）"}`），`/api/files` 与 `/api/health`
  照常工作（`/api/health` 增加 `"recorderd": true|false` 便于排障）。前端既有能力即可表达：
  逐模块错误 + 「部分数据同步失败 + 重试」。

## 取舍

- **重启语义变了**：重启 WebUI 不再打断录制；**重启 recorderd 仍会**（SIGTERM → 并行
  `request_stop` → ffmpeg 收尾当前分段，代码内上限 45s，单元 `TimeoutStopSec=75s`），
  这是"要换引擎代码/换参数"时才需要的动作。
- **多一层本地调用**：每次任务操作多一次 unix socket 往返（毫秒级）；`/api/jobs` 5s 轮询
  也是本地调用，开销可忽略。recorderd 的请求日志默认静默（`RECORDERD_VERBOSE=1` 打开）。
- **`pid` / `memory` 语义**：任务状态里的 `pid`/`memory` 现在描述**引擎宿主进程**
  （线程与进程共享 RSS，无法按任务切分）。字段名保持不变以维持前端契约。
- **概览是全或无**：`/api/overview` 依赖任务列表，recorderd 不可达时整个接口 503
  （磁盘/文件信息也一起不可见），而不是把任务数当成 0 —— 规范要求「未知不得以零冒充」。
- **socket 位置**：默认放 `state/run/`，两个服务都以 `ubuntu` 运行，靠 0700/0600 权限隔离；
  可用 `RECORDERD_SOCKET` 覆盖（例如放 `/run/livestream-recorderd/`）。
  注意 `state/` 被清理时 socket 会消失，需要重启 recorderd。
- 前端与 `webui/index.html` 完全未受影响。

## 升级与回滚

升级（`sudo bash systemd/install.sh`，脚本已按此顺序实现）：

```bash
systemctl daemon-reload
systemctl stop    livestream-webui       # 旧版进程自己托管引擎：必须先停，否则两边同时录制
systemctl enable --now livestream-recorderd   # 恢复全部未暂停任务
systemctl enable --now livestream-webui       # UI 起来后转发到控制面
```

- 中断窗口 = 停旧 UI（收尾当前分段，通常数秒）+ recorderd 恢复任务（秒级）。
- 任务目录格式未变，回滚只需 `git checkout <旧提交> && sudo bash systemd/install.sh`
  （脚本会先停 WebUI 再按旧模型恢复任务）。

## 验证

- 单测：`tests/test_webui.py`
  - `ControlPlaneTest`：在临时 unix socket 上真起 recorderd 的 HTTP 层，用 `control.py`
    跑通 health/jobs/start/pause/resume/restart/delete/logs 与错误映射（两侧都断言）。
  - `WebUIDegradedTest`：recorderd 不可达时 `/api/jobs`→503、`/api/overview`→503、
    控制类 POST→503、`/api/files`→200、`/api/health`→`{"ok":true,"recorderd":false}`。
  - 原有 `RecorderStatusTest` / `TaskPauseResumeDeleteTest` 等引擎与目录语义用例保持不变。
- 进程级实测（临时目录 + 真实引擎，离线频道）：
  - recorderd 恢复任务并运行引擎；WebUI 通过 socket 读到同一份状态；
  - **重启 WebUI 前后**：recorderd PID 不变、任务 `started` 不变、recorderd 日志中
    `已恢复` 仍只有 1 次 → 引擎与任务线程完全未受影响；
  - 停掉 recorderd：`/api/jobs`/`/api/overview`/`/api/logs`/控制 POST 全部 503、
    `/api/files` 与 `/api/health` 正常；重新拉起后自动恢复。
