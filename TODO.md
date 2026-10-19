# 待办

> **重启语义（2026-10-19 起拆成两个服务）**：`systemctl restart livestream-webui` **不影响录制**；
> 引擎侧改动（`scripts/`、`webui/recorder.py`、`webui/jobs.py` 等）需要重启
> `livestream-recorderd`（会优雅收尾当前分段并按任务目录恢复全部未暂停任务）。
> 见 [ADR 0002](docs/adr/0002-recorderd-split.md)。下面 10-06 那条记录里的“重启 WebUI”是拆分前的写法。

## 本轮（2026-10-19）已完成

- [x] 前端改为 Lit 原生 ESM、去掉 Vue/Vite 构建链（`3784a75`，[ADR 0001](docs/adr/0001-webui-frontend-lit.md)）：
      lit@3 走 CDN + 仓库内 vendor 回落，`webui/index.html` 退化为静态壳。
- [x] 录制引擎拆为独立控制面 `livestream-recorderd`（`c743c64`，[ADR 0002](docs/adr/0002-recorderd-split.md)）。
  - 2026-10-19 05:59 UTC 完成切换（当时 0 频道在录，无损）：恢复 45 个任务、保留 8 个暂停；
    实测重启 WebUI 耗时 0.03s，recorderd PID 与全部任务 `started` 不变。
- [x] 文档：结构/使用/配置/排障/设计规范同步，新增 ADR 0001、0002、0003 与
      `docs/structure.md` §流程（4 张 Mermaid 图）；`state/tasks.json` 的“非实时接口”
      语义已由测试钉住（`test_catalog_edits_do_not_control_running_tasks`）。

## 待办

- [ ] 前端历史文案更新（已在[设计规范 §9](docs/webui-design-spec.md) 记录为验收项）：
  - 任务详情「该任务当前不在 systemd 单元列表中」→ 改为「不在任务列表中」；
  - 日志面板副标题「Journal 实时输出」→ 改为引擎日志（如「引擎实时输出」）；
  - 暂停／重启确认框「最长 30 秒」→ 改为“短 join 最长 5 秒等引擎收尾当前分段”。
  - 注意：改用户可见文案前先确认引擎真实收尾时间口径（`Recorder.stop(timeout=5)` +
    `TimeoutStopSec=75s` 的差别）。

- [ ] `webui/frontend/api.js` 顶部注释仍写「停止/重启要等 systemd 收尾（服务端最长 35s）」：
  改为「控制类调用要等引擎收尾（短 join 5s；前端超时放宽到 40s 留余量）」。一行注释，无风险。

- [ ] `state/tasks.json` 增加 `.bak` 兜底：`_save_catalog()` 成功后保留一份副本，
  `_load_catalog()` 主文件解析失败时回退到副本（当前损坏按空目录处理 → 下次 recorderd
  重启会丢失全部任务记录）。约 10 行 + 1 个测试。

- [ ] （可选）任务目录外部改动检测：记录 mtime/内容 hash，发现被外部修改时**只写一条日志**
  提醒「改动将在 recorderd 重启后生效」，不做任何启停。约 30 行。
  背景：现在文件变更完全不影响运行中的任务（命令式设计，见
  [ADR 0003](docs/adr/0003-imperative-task-control.md)），静默不一致容易让人误以为
  改文件就能改任务。

- [ ] （可选）删除录像文件前询问控制面「该文件是否正在写入」，避免删到正在录的分段。
  背景：删除由 WebUI 直接 `unlink`（`files.delete_file`），recorderd 不知情；
  引擎的 `_watch_dir` 只自愈目录，不保护单个文件。

- [ ] 昵称缓存改为直接 K/V 映射，替代当前按哈希命名的独立 JSON 文件。
  - Key 使用「平台:频道标识」，Value 使用昵称，保留本地优先、获取成功后保存的策略。
  - 兼容迁移现有 `.nicknames/` 缓存，并处理多频道并发写入，避免数据覆盖。
  - 暂不实施，现有代码与服务保持不变。

- [ ] 下次 TikTok 开播时验证原画录制与转推（`fff0e89`、`febd4d9`）。
  - 2026-10-15 已在无录制时重启（当时还是单进程模型）；`bili-live.service` 下次自动拉起即生效。
  - 录制：新分段 `ffprobe` 应为 `hevc`（原画）；检查分段时长连续、无只有音频的分段，记录每小时文件大小。
  - 转推：`bili/logs/ffmpeg_tiktok_*.log` 开头输入流应为 `Video: hevc`，`speed=1x` 稳定，CPU 余量充足。
  - 文件轮播含 H.265 录制时应自动重编码（日志出现“检测到非 H.264 视频”）。
  - 2026-10-15 用 `eunsolp`（原画 1080p30 H.265）手动验证：录制取流拿到原画，按引擎参数分段录 3 分钟，3 段约 180 秒连续、解码无错、约 5 Mbps（约 2.2 GB/小时）；`push.sh` 取流拿到原画，转推流程实时 60 秒 CPU 约 81% 单核、`speed=1x`；比拉 hd 档 PSNR 高约 1.9 dB。尚待真实服务（WebUI 录制任务、`bili-live.service`）跑一场确认。
  - 2026-10-16 改用 BtbN 9.0.2 稳定版（原 master 构建已于 2026-10-16 删除）：`mirei_kamio`（原画 960×1920 25fps H.265）上 9.0.2 解码、分段录 60 秒、转推实时 60 秒均正常，转推 CPU 约 101%，与 master 的 104% 一致。

## 已完成（历史记录）

- [x] 等待无直播录制时部署并重启 WebUI，使 TikTok 首轮兜底和离线状态修复（`ec9fbed`）生效。
  - 执行前确认所有任务均未处于录制状态，且没有运行中的 ffmpeg 录制进程；有录制时继续等待。
  - 已于 2026-10-06 16:49:58 UTC 完成：重启前 38 个任务均未录制且没有 ffmpeg 录制进程；重启后服务 active、健康检查通过，`morihinachan` 首轮启用浏览器兜底并正确显示“确认未开播”。
