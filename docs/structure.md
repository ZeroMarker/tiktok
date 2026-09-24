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

每平台的 `record.sh` 均为薄包装，只转发给引擎：

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

`webui/app.py`（常驻 systemd 服务）通过 `systemd-run` 按需生成每频道临时单元
`livestream-rec-{platform}-{channel}.service`，调用各平台 `record.sh`。
后端实现拆分为 `webui/{config,jobs,files,stats,server}.py`（配置 / 任务与 systemd
操作 / 录制文件 / 概览聚合 / HTTP 层），`app.py` 仅为兼容门面与直接执行入口；
跨模块配置一律经 `config.X` 运行时读取，便于测试在定义处 patch。
临时单元带 `KillMode=mixed`、`TimeoutStopSec=30s`、网络就绪依赖与崩溃自动重启。
`KillMode=mixed` 只把 SIGTERM 发给主进程（bash→python 引擎），由引擎给 ffmpeg 收尾当前
分段后再退出；引擎的信号处理器在 C 回调栈（curl_cffi）里也直接 `os._exit`，因此停止请求
不会等到 `TimeoutStopSec` 到期才生效。控制类接口（暂停/继续/重启/删除）超时设为 35s
（`CONTROL_TIMEOUT`），前端对应请求也与之对齐。

**任务目录（`state/tasks.json`）**：`systemd-run --collect` 创建的单元在停止后即被 systemd
回收（对已回收单元 `systemctl start` 会报 "Unit not found"）。因此 WebUI 在创建任务时把
启动参数（平台/频道/画质/Cookie）写入任务目录；「暂停」置 `paused=true`，「继续」按记录重建
同名单元，「删除」清理记录。WebUI 启动时会把目录作为期望状态，自动重建所有缺失且未暂停的
任务，因此服务器重启后任务会恢复；已暂停任务不会自动启动。单个任务恢复失败只写入服务日志，
不会删除其目录记录或阻止 WebUI 启动。目录读取失败或损坏时按空目录处理，不影响其他功能。
文件为运行产物（已 gitignore），路径可用 `WEBUI_STATE_DIR`/`STATE_DIRECTORY` 覆盖；
服务单元通过 `ReadWritePaths=.../state` 放行写入。

**运行用户**：录制服务应以安装了 yt-dlp/curl_cffi 的普通用户运行（本部署为
`ubuntu`，依赖其 `~/.local` 站点目录），否则子进程 yt-dlp 会因找不到 `yt_dlp`
模块而静默失败，导致所有 yt-dlp 抓流方法失效。本仓库 `tk/record.sh` 会为子进程
自动补充该用户的 `PYTHONPATH`/`PATH` 作为兜底。

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
