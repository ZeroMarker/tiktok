# Live Stream Toolkit

用于无人值守录制直播，或将直播源转推到 Bilibili。

## 支持范围

- TikTok：本地分段录制、转推 Bilibili
- SOOP：本地分段录制、转推 Bilibili
- Kick：本地分段录制
- YouTube：本地分段录制、转推 Bilibili
- CHZZK：本地分段录制
- Twitch：本地分段录制、转推 Bilibili

## 快速开始

完整的依赖清单、Python 环境要求、Chromium 路径和验证步骤见
[外部依赖](docs/configuration.md#外部依赖)。本机 FFmpeg 已切换到 BtbN 9.0 稳定分支
构建，版本、安装路径与选择规则见 [FFmpeg 配置](docs/configuration.md#新版-ffmpegtiktok-原画可选)。

安装独立取流工具（后端直接导入的 Python 包还需按上述文档配置）：

```bash
uv venv
uv tool install "yt-dlp[default,curl-cffi]"
```

检测命令：

```bash
yt-dlp --version
ffmpeg -version
python --version
```

录制 TikTok：

```bash
bash platforms/tiktok/record.sh <tiktok_username>
```

部分 TikTok 主播需要登录态，把浏览器导出的 Netscape Cookie 存为项目根 `cookies.txt`
（已 .gitignore 忽略），`record.sh` 会自动携带；详见 [使用说明](docs/usage.md)。

录制 SOOP：

```bash
bash platforms/soop/record.sh <soop_username|SOOP直播链接>
```

录制 Kick、YouTube、CHZZK 或 Twitch：

```bash
bash platforms/kick/record.sh <Kick用户名|直播URL>
bash platforms/youtube/record.sh <YouTube handle|直播URL>
bash platforms/chzzk/record.sh <CHZZK频道ID|直播URL>
bash platforms/twitch/record.sh <Twitch用户名|频道URL>
```

转推 Bilibili（开播、推流、轮播）见本仓库 [`bili/`](bili/README.md)（含开播/停播/改标题、直播推流、文件轮播、轮播值守与管理页；管理页把推流目标固定成一个 TikTok 主播并实时监测开播状态，开播自动转推、关播自动停推）；把录制文件投成 B 站稿件用同目录的 `bili/upload.py`。

平台脚本统一在 `platforms/<平台>/` 下（如 `platforms/tiktok/record.sh`）。根目录曾有的散脚本 `start.sh`（取流检测）与 `yt.sh`（YouTube 转推）已移入 [`archive/`](archive/README.md)。

## WebUI 与 systemd

安装并启动本机管理页面：

```bash
sudo bash systemd/install.sh
```

`install.sh` 同时部署并启用共享浏览器渲染服务 `tiktok-browserd`（TikTok 检测的浏览器
兜底依赖它；缺失时该兜底自动跳过，轻量检测与 yt-dlp 路径不受影响），以及录制控制面
`livestream-recorderd`。

录制执行是**两进程**（见 [ADR 0002](docs/adr/0002-recorderd-split.md)）：

- `livestream-recorderd.service`（`webui/recorderd.py`）= 引擎宿主：每个任务是它进程内的
  引擎线程，任务目录 `state/tasks.json` 由它独占写入，控制面只监听本地 unix socket
  （`state/run/recorderd.sock`）。
- `livestream-webui.service`（`webui/app.py`）= 静态资源 + `/api/*`，任务状态与控制转发给
  控制面。

因此**重启 WebUI 不会打断录制**（改前端、调端口、升级 UI 都安全）；**重启 recorderd 会**
（SIGTERM → 引擎收尾当前分段 → 启动时按任务目录恢复全部未暂停任务），它也是"换引擎代码/
换参数"时用的动作：`sudo systemctl restart livestream-recorderd`。

WebUI 后端默认监听 `127.0.0.1:8766`，应用层不校验令牌。若通过 Caddy 对外提供服务，必须在反向代理层启用 Basic Auth 或等效访问控制；最小配置片段见[配置说明](docs/configuration.md#caddy-反向代理)。真实的 `/etc/caddy/Caddyfile` 属于服务器配置，不由本仓库安装或覆盖。

不开放公网时也可以使用 SSH 隧道：

```bash
ssh -L 8765:127.0.0.1:8766 <server>
```

然后打开 `http://127.0.0.1:8765`。

WebUI 同时提供 PWA 支持：可安装到桌面/主屏幕，断网时仍可打开界面（任务数据在联网后自动刷新）。
前端资源（`manifest.webmanifest`、`sw.js`、图标，以及 `frontend/` 应用模块与 `vendor/` 回落）
都在 `webui/` 目录下，`sw.js` 会预缓存应用壳与 vendor 闭包，配合 Caddy 路径剥离可正常工作。

## 常用文档

- [项目结构](docs/structure.md)
- [配置与外部依赖](docs/configuration.md)
- [使用说明](docs/usage.md)
- [WebUI 设计规范](docs/webui-design-spec.md)
- [ADR 0001：WebUI 前端采用 Lit、去掉构建链](docs/adr/0001-webui-frontend-lit.md)
- [ADR 0002：录制引擎拆为独立控制面 recorderd](docs/adr/0002-recorderd-split.md)
- [排障](docs/troubleshooting.md)
- [Bilibili 推流与投稿](bili/README.md)
- [Bilibili 投稿接口细节](bili/docs/bilibili-upload-api.md)
- [归档：TikTok 录制历史排障记录](docs/archive/tiktok-live-recording.md)
- [归档：B 站推流音画不同步的定位与修复](docs/archive/bili-push-av-sync.md)
- [封存：根目录散脚本](archive/README.md)

## 开发与测试

全部 Python 单元测试基于标准库 `unittest`，**无需安装额外依赖**：

```bash
bash test.sh    # 运行 tests/ 与 bili/tests/ 两套测试
```

前端（`webui/frontend/`）是**原生 Web Components + Lit 3**，以 ESM + import map 直接运行，
没有 npm / bundler / 构建产物：改完源码刷新页面即可，`webui/index.html` 只是静态壳页面
（由引导脚本注入 import map 并加载入口模块）。lit@3 默认从 CDN（esm.sh）加载，离线或
CDN 不可达时回落到仓库内 `webui/vendor/` 的最小闭包。

CI（`.github/workflows/checks.yml`）在每次 push / PR 校验：两套单元测试、全部 shell
脚本语法（`bash -n`）。前端没有构建步骤，模块路径、import map 与 vendor 闭包由单元测试
（`tests/test_webui.py` 的 `FrontendModuleGraphTest`）保证可解析。

本地想逐项手动复现 CI 的检查（不依赖 `test.sh`）：

```bash
python3 -m unittest discover -s tests -v
python3 -m unittest discover -s bili/tests -v
find . -name '*.sh' -type f -print \
  | while IFS= read -r script; do bash -n "$script"; done
```

## 运行产物

录制输出按平台分目录，再按账号创建频道目录，每 10 分钟生成一个 MP4 文件（文件名不含平台前缀）。日志默认写入 `recordings/logs/<平台>/`。

仓库已忽略日志、视频文件、Cookie 文件、`bili/upload-state*.json`（投稿凭证）和 `recordings/`。建议长期任务在仓库外或 `recordings/` 下运行，避免运行产物和源码混在一起。

WebUI 创建的任务统一使用 `RECORDINGS_DIR`；概览页的磁盘容量与最近文件也以该目录为准。

FFmpeg 录制和轮播默认仅记录 warning/error，关闭常规进度输出；TikTok 转推每
10 秒保留一条进度心跳，供 60 秒假死看门狗使用。脚本在下次启动时应用这些参数；
引擎侧的此类改动需要重启 `livestream-recorderd` 服务后生效（重启 WebUI 不影响录制），
可等当前录制结束再重启。

`systemd/install.sh` 同时安装日志轮转（需要系统已安装 `logrotate`）；已有部署可单独运行：

```bash
sudo bash systemd/install-logrotate.sh
# 自定义录制目录需与 WebUI 配置一致：
sudo RECORDINGS_DIR=/data/recordings bash systemd/install-logrotate.sh
```

每小时检查根目录 `logs/`、`bili/logs/` 和录制目录 `logs/<平台>/`，每天或单文件
超过 20 MiB 时轮转，压缩并保留最多 7 份备份；在发生轮转时清理修改时间超过
14 天的压缩备份。按日期命名且不再写入的日志也会被压缩，空的原文件不占用
日志内容空间。`copytruncate` 兼容 FFmpeg 已打开的文件句柄，复制与截断之间
可能丢失少量日志；20 MiB 为检查阈值，小时内可暂时超过。系统 journal 使用其
自身的保留策略，本配置不清理 journal。安装过程不会立即轮转或清理其他日志。
