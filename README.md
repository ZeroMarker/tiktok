# Live Stream Toolkit

用于无人值守录制直播，或将直播源转推到 Bilibili。

本分支（`rust-rewrite`）以 Rust 重写统一录制引擎，并新增桌面端管理功能；
Python 版 WebUI/转推脚本仍保留可用，详见下文「Rust 版」。

## 支持范围

- TikTok：本地分段录制、转推 Bilibili
- 抖音：本地分段录制
- SOOP：本地分段录制、转推 Bilibili
- Kick：本地分段录制
- YouTube：本地分段录制、转推 Bilibili
- CHZZK：本地分段录制
- Twitch：转推 Bilibili

## Rust 版（本分支新增）

Rust 工作区位于 `crates/`，覆盖 Python `scripts/dlr.py` 的全部录制能力：

```text
crates/
├── dlr-core/     # 统一引擎：检测循环、ffmpeg 分段、优雅停止、目录自愈
│                 #   平台适配器：tiktok / douyin / youtube / kick / chzzk / soop
│                 #   CLI 入口（dlr 二进制）
└── dlr-desktop/  # egui 桌面端（dlr-desktop 二进制）：任务管理 + 日志 + 录制文件
```

构建：

```bash
cargo build --release
# 产物：target/release/dlr（CLI）、target/release/dlr-desktop（桌面端）
```

CLI 与 Python 版用法一致：

```bash
target/release/dlr tiktok <username> [--cookies cookies.txt] \
  [--recordings-dir recordings] [--segment-seconds 600]
target/release/dlr youtube <handle|直播URL>
```

桌面端（新增功能）：进程内线程运行引擎，不依赖 systemd，可直接在桌面机使用。
提供任务添加/停止/删除、实时状态与日志、录制文件浏览/删除、参数设置
（录制目录、分段时长、重试间隔、Cookie）。设置持久化在
`~/.config/dlr-desktop/config.json`。中文界面字体自动从系统
CJK 字体加载（如 Noto Sans CJK / 文泉驿）。

Python 引擎与 WebUI 不受影响，仍按下文使用。

## 快速开始

初始化依赖：

```bash
uv venv
uv tool install "yt-dlp[default,curl-cffi]"
git submodule update --init --recursive
```

检测命令：

```bash
yt-dlp --version
ffmpeg -version
python --version
```

录制 TikTok：

```bash
bash tk/record.sh <tiktok_username>
```

部分 TikTok 主播需要登录态，把浏览器导出的 Netscape Cookie 存为项目根 `cookies.txt`
（已 .gitignore 忽略），`record.sh` 会自动携带；详见 [使用说明](docs/usage.md)。

录制抖音：

```bash
bash douyin/record.sh <web_rid|抖音号|完整URL>
```

录制 SOOP：

```bash
bash soop/record.sh <soop_username|SOOP直播链接>
```

录制 Kick、YouTube 或 CHZZK：

```bash
bash kick/record.sh <Kick用户名|直播URL>
bash youtube/record.sh <YouTube handle|直播URL>
bash chzzk/record.sh <CHZZK频道ID|直播URL>
```

抖音需要登录态时，可以从本机浏览器导出 Cookie：

```bash
bash douyin/import_cookies.sh chrome
bash douyin/record.sh <直播间> --cookies douyin-cookies.txt
```

转推前先配置 Bilibili 推流地址，详见 [配置](docs/configuration.md)。

## WebUI 与 systemd

安装并启动本机管理页面：

```bash
sudo bash systemd/install.sh
```

WebUI 后端默认监听 `127.0.0.1:8766`，应用层不校验令牌。若通过 Caddy 对外提供服务，必须在反向代理层启用 Basic Auth 或等效访问控制；最小配置片段见[配置说明](docs/configuration.md#caddy-反向代理)。真实的 `/etc/caddy/Caddyfile` 属于服务器配置，不由本仓库安装或覆盖。

不开放公网时也可以使用 SSH 隧道：

```bash
ssh -L 8765:127.0.0.1:8766 <server>
```

然后打开 `http://127.0.0.1:8765`。

WebUI 同时提供 PWA 支持：可安装到桌面/主屏幕，断网时仍可打开界面（任务数据在联网后自动刷新）。前端资源（`manifest.webmanifest`、`sw.js`、图标）在 `webui/` 目录下，配合 Caddy 路径剥离可正常工作。

## 常用文档

- [项目结构](docs/structure.md)
- [配置](docs/configuration.md)
- [使用说明](docs/usage.md)
- [排障](docs/troubleshooting.md)
- [TikTok 直播录制使用与排障](docs/tiktok-live-recording.md)
- [B站视频上传接口文档](docs/bilibili-upload-api.md)

## 运行产物

录制脚本会按账号创建输出目录，并每 10 分钟生成一个 MP4 文件。日志默认写入对应 `logs/` 目录。

仓库已忽略日志、视频文件、Cookie 文件和 `recordings/`。建议长期任务在仓库外或 `recordings/` 下运行，避免运行产物和源码混在一起。

WebUI 创建的任务统一使用 `RECORDINGS_DIR`；概览页的磁盘容量与最近文件也以该目录为准。

## 开发检查

```bash
python3 -m unittest discover -s tests -v
find . -path './douyin/DouyinLiveRecorder' -prune -o -name '*.sh' -type f -print \
  | while IFS= read -r script; do bash -n "$script"; done
```

推送后 GitHub Actions 会自动执行相同检查。
