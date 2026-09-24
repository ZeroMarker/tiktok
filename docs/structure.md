# 项目结构

本项目按平台和用途组织代码，根目录只保留项目入口、说明和跨平台脚本。

## 统一录制引擎（核心）

所有平台的无人值守录制统一由 Python 引擎实现，平台差异收敛为"适配器"：

```text
scripts/
├── dlr.py                 # 引擎入口：python3 scripts/dlr.py <platform> <target> [选项]
├── browserd.py            # 共享常驻 Chromium 渲染服务（所有引擎复用，CDP over pipe）
└── dlr/
    ├── engine.py          # 统一录制循环：输出布局、检测、ffmpeg 分段、优雅停止、断流重试
    └── adapters/
        ├── base.py        # 适配器接口 + 频道标识提取
        ├── ytdlp.py       # youtube / kick / chzzk / soop（yt-dlp 通用，含 impersonate 兜底）
        ├── tiktok.py      # TikTok：轻量检测每轮先行（带 Cookie），升级轮才跑 yt-dlp 与浏览器
        ├── tiktok_extract.py  # TikTok 取流（curl_cffi 页面 + webcast API；渲染走 browserd）
        └── douyin.py      # 抖音：复用 douyin/get_stream.py（DouyinLiveRecorder 子模块）
```

每平台的 `record.sh` 均为薄包装，只转发给引擎（单进程 WebUI 不经此包装、直接构造引擎；包装保留给命令行手动使用）：

```bash
exec python3 "${SCRIPT_DIR}/../scripts/dlr.py" <platform> "$@"
```

支持平台：`youtube kick chzzk soop tiktok douyin`

## 平台目录

```text
├── tk/                    # TikTok（record.sh 转发入口）
├── douyin/                # 抖音（record.sh + get_stream.py，依赖子模块 DouyinLiveRecorder）
├── soop/                  # SOOP（record.sh 入口）
├── youtube/               # YouTube（record.sh 入口）
├── kick/                  # Kick（record.sh 入口）
├── chzzk/                 # CHZZK（record.sh 入口）
├── twitch/                # Twitch -> Bilibili 脚本
├── bili/                  # Bilibili 推流（开播/推流/轮播/值守 + 独立 WebUI 与 user 单元，见 bili/README.md）
├── scripts/               # 统一录制引擎（见上）
├── systemd/               # WebUI/browserd systemd unit 与安装脚本
├── tests/                 # WebUI 与引擎单元测试（bili/ 另有 bili/tests/，由 test.sh 一并运行）
├── webui/                 # 本地录制任务管理页面与 API
├── docs/                  # 使用、配置、排障和维护文档
├── start.sh               # TikTok 直播源快速检测入口
├── yt.sh                  # YouTube -> Bilibili 脚本
└── test.sh                # 运行仓库全部单元测试（tests/ + bili/tests/，纯标准库）
```

## 运行产物

录制输出统一到 `RECORDINGS_DIR`（systemd 环境默认 `/home/ubuntu/tiktok/recordings`，
手动运行默认 `./recordings`），按平台分目录，平台下按 `{channel}[_{nickname}]/` 建频道目录：
每个频道只会出现一个目录——昵称在目录确定前每轮补抓（进程重启后从首轮
重新抓，不依赖内存记忆），直到开播首轮仍无昵称才回退为纯 `{channel}/`；
且目录名在本场录制首轮确定后固定，不会中途改名分裂。

```text
recordings/
├── tiktok/
│   ├── emiri.okazaki/          # 昵称抓取失败时的退化命名
│   └── emiri.okazaki_エミリ/    # 正常命名（每个频道二选一，不会同时存在）
├── soop/
│   └── playerid_Nickname/
├── youtube/
│   └── ChannelName/
└── logs/                      # ffmpeg 运行日志（按平台分目录）
    ├── tiktok/
    │   └── ffmpeg_record_emiri.okazaki_20260823.log
    ├── soop/
    └── youtube/
```

分段文件名 `{channel}[_{nickname}]_%Y%m%d_%H%M%S.mp4`，不含平台前缀（平台已在目录层级体现）。

WebUI 的最近文件列表扫描 `RECORDINGS_DIR`，不会遍历整个仓库。仓库已忽略
`recordings/`、`logs/`、`*.mp4` 等运行产物。

**目录自愈**：录制引擎会对输出目录做健壮性保护——每次录制回合启动前以及整个
录制期间都会确认输出目录存在；即使目录（含父目录，如整块 `recordings/`）被外部
删除/清理，也会在 ffmpeg 写下一个分段前自动重建，不影响持续录制。因此空目录、
占位目录可以直接删除，无需保留。

## 控制面

录制执行是**单进程模型**：`webui/app.py`（常驻 systemd 服务 `livestream-webui.service`，
以 `ubuntu` 运行）在自身进程内调度所有频道——每个任务是一个引擎线程
（`webui/recorder.py` 驱动 `scripts/dlr/engine.py` 的 `Engine`），不再按频道创建
systemd 临时单元，也不再经 `record.sh` 包装（包装仅保留给命令行手动使用）。

后端实现拆分为 `webui/{config,jobs,files,stats,server,recorder}.py`（配置 / 任务编排与
任务目录 / 录制文件 / 概览聚合 / HTTP 层 / 引擎线程调度），`app.py` 仅为兼容门面与
直接执行入口；跨模块配置一律经 `config.X` 运行时读取，便于测试在定义处 patch。

生命周期语义与旧多进程模型一一对等：

- **优雅停止**：暂停/删除/停服都会对每个引擎 `request_stop()`——置停止位、中断长等待
  （检测间隔可长达 5 分钟）、立即向 ffmpeg 发终止信号收尾当前分段。控制类操作（暂停/
  删除/重启）短 join 最长 5 秒：引擎若正阻在网络调用（页面抓取超时可达 20s）里，超时
  即返回、线程后台自行退出并从任务表自摘，API 不挂起；停服（SIGTERM/SIGINT）则并行
  join 全部引擎（单元 `TimeoutStopSec=60s` 兜底）。命令行路径（dlr.py）仍由引擎信号
  处理器直接 `os._exit`，停止不会等到超时才生效。
- **崩溃自动重启**：引擎线程内未捕获异常按 10 秒退避重建（等价旧
  `Restart=on-failure RestartSec=10s`），重启计数即任务状态里的 `restarts`。
- **状态**：`active/running`（检测或录制中）、`active/activating`（构建/退避窗口）、
  `active/deactivating`（停止收尾）、`failed`、`paused`；`live` 由引擎
  `phase == recording 且 ffmpeg 存活` 直接判定，不再扫描 /proc 进程树。

**任务目录（`state/tasks.json`）**：仍是期望状态与参数持久化——创建任务时写入启动
参数（平台/频道/画质/Cookie），「暂停」置 `paused=true`（参数留存、线程停止），
「继续」按记录重建线程，「删除」清理记录。WebUI 启动时把目录作为期望状态恢复所有
未暂停任务，因此服务器重启后任务会恢复；已暂停任务不会自动启动。单个任务恢复失败
只写入服务日志，不会删除其目录记录或阻止 WebUI 启动。目录读取失败或损坏时按空目录
处理，不影响其他功能。`livestream-rec-*.service` 命名仅作为稳定任务 ID 沿用
（目录键、日志文件名、API 字段），历史数据零迁移。**列表接口** = 运行任务的进程内
状态快照（`recorder.status()`）拼上目录里 `paused:true` 的条目，两者字段形状一致
（前端零改动）；因此暂停任务重启后仍显示，运行任务的状态永远来自真实线程而非缓存。
文件为运行产物（已 gitignore），
路径可用 `WEBUI_STATE_DIR`/`STATE_DIRECTORY` 覆盖；服务单元通过
`ReadWritePaths=.../state` 放行写入。

**任务日志**：每个引擎的输出写入 `recordings/logs/<平台>/engine_<任务ID>.log`
（WebUI 日志面板读取，尾部上限 5000 行/100KB），同时带 `[平台:频道]` 前缀镜像到
服务 stdout（`journalctl -u livestream-webui -f` 可整体回看）；ffmpeg 自身日志仍按
`ffmpeg_record_*.log` 分文件。

**运行用户**：`livestream-webui.service` 以 `ubuntu` 运行（与 browserd 一致），
原生使用其 `~/.local` 下的 yt-dlp / curl_cffi；换用户运行时需自行保证依赖可见。
旧版每频道单元靠 `tk/record.sh` 等包装桥接 `PYTHONPATH`/`PATH`，该兜底仅对命令行
入口保留。

**共享浏览器（`tiktok-browserd.service`）**：TikTok 检测的浏览器兜底统一走
`scripts/dlr/browserd.py`（`127.0.0.1:9555`，`TIKTOK_BROWSERD_URL` 可覆盖）：
一个常驻 Chromium 通过 CDP（`--remote-debugging-pipe`）为所有引擎开标签页渲染，
替代每轮冷启动浏览器（曾 ~247 次/小时、≈0.5 核 CPU）。由 `systemd/install.sh`
安装并启用；服务不可用时引擎自动跳过浏览器兜底，轻量检测与 yt-dlp 路径不受影响。

**登录 Cookie**：TikTok 部分主播要求登录态才能拿到直播流（无 Cookie 时
yt-dlp / Web API 均判“未开播”）。`tk/record.sh` 会检测项目根 `cookies.txt`
（Netscape 格式，已被 `.gitignore` 忽略），存在时自动附带 `--cookies` 给引擎，
由适配器透传给 yt-dlp；Cookie 与 Bilibili 推流码等敏感信息不要提交仓库。

## 子模块

`douyin/DouyinLiveRecorder` 是 Git 子模块。首次克隆后需要初始化：

```bash
git submodule update --init --recursive
```

更新子模块：

```bash
git submodule update --remote douyin/DouyinLiveRecorder
```
