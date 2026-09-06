# 项目结构

本项目按平台和用途组织代码，根目录只保留项目入口、说明和跨平台脚本。

## 统一录制引擎（核心）

所有平台的无人值守录制统一由 Python 引擎实现，平台差异收敛为"适配器"：

```text
scripts/
├── dlr.py                 # 引擎入口：python3 scripts/dlr.py <platform> <target> [选项]
└── dlr/
    ├── engine.py          # 统一录制循环：输出布局、检测、ffmpeg 分段、优雅停止、断流重试
    └── adapters/
        ├── base.py        # 适配器接口 + 频道标识提取
        ├── ytdlp.py       # youtube / kick / chzzk / soop（yt-dlp 通用，含 impersonate 兜底）
        ├── tiktok.py      # TikTok：yt-dlp → impersonate → mobile → curl_cffi 四方法兜底
        ├── tiktok_extract.py  # TikTok 兜底取流（curl_cffi 解析页面 + webcast API）
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
├── bili/                  # Bilibili：live.py 开播工具（扫码登录/开闭直播间/取推流码）+ push.sh/soop.sh 转推 + replay.sh 本地文件轮播
├── twitch/                # Twitch -> Bilibili 脚本
├── scripts/               # 统一录制引擎（见上）
├── systemd/               # WebUI systemd unit 与安装脚本
├── tests/                 # WebUI 与引擎单元测试
├── webui/                 # 本地录制任务管理页面与 API
├── docs/                  # 使用、配置、排障和维护文档
├── start.sh               # TikTok 直播源快速检测入口
└── yt.sh                  # YouTube -> Bilibili 脚本
```

## 运行产物

录制输出统一到 `RECORDINGS_DIR`（systemd 环境默认 `/home/ubuntu/tiktok/recordings`，
手动运行默认 `./recordings`），按平台分目录，平台下按 `{channel}[_{nickname}]/` 建频道目录：

```text
recordings/
├── tiktok/
│   ├── emiri.okazaki/
│   └── emiri.okazaki_エミリ/
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
临时单元带 `KillMode=mixed`、`TimeoutStopSec=30s`、网络就绪依赖与崩溃自动重启。

**运行用户**：录制服务应以安装了 yt-dlp/curl_cffi 的普通用户运行（本部署为
`ubuntu`，依赖其 `~/.local` 站点目录），否则子进程 yt-dlp 会因找不到 `yt_dlp`
模块而静默失败，导致所有 yt-dlp 抓流方法失效。本仓库 `tk/record.sh` 会为子进程
自动补充该用户的 `PYTHONPATH`/`PATH` 作为兜底。

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
