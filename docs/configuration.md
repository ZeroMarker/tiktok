# 配置

## 外部依赖

### 依赖清单与适用范围

当前脚本和 systemd 部署面向 Linux，Shell 入口需要 Bash；PowerShell 不能直接替代
Bash 执行这些 `.sh` 文件。Python 主体、WebUI 后端及 Bilibili 登录/投稿接口使用
标准库，没有数据库、Redis 或独立 Web 框架依赖。

| 依赖 | 使用场景 | 要求 |
|---|---|---|
| Python 3 | 录制引擎、WebUI、Bilibili 接口 | 必需；CI 使用 Python 3.12，建议与之保持一致 |
| Bash、常用 Linux 命令 | 平台入口、推流、服务安装 | 使用 Shell 脚本时需要；包括 `sed`、`grep`、`find`、`ps`、`pkill` 等 |
| FFmpeg / ffprobe | 录制、分段、转推、轮播媒体检测 | 本机已使用 BtbN 9.0 稳定分支构建；ffprobe 用于轮播编码检测；路径与验证见下方 FFmpeg 一节 |
| yt-dlp | 各平台直播源解析 | 录制/平台转推的核心依赖；安装 `default,curl-cffi` extras |
| curl_cffi | TikTok 进程内检测、页面解析，以及 yt-dlp 的浏览器模拟请求 | TikTok 轻量检测需要；缺失时部分解析路径不可用 |
| Chromium 或 Google Chrome | TikTok 共享浏览器渲染、YouTube 登录态取流 | 浏览器路径需要；不可用时相应路径失败并尝试其他可用检测方式 |
| Node.js 22+、yt-dlp-ejs | YouTube 浏览器取流和 HLS 地址的 `n` 校验值解算 | YouTube 浏览器路径需要；EJS 随 yt-dlp 的 `default` extra 安装，需与 yt-dlp 匹配 |
| uv | 创建 Python 环境和安装依赖 | 安装工具，程序运行时不要求 uv 常驻 |
| systemd、logrotate | 后台服务、日志轮转 | 使用 `systemd/install.sh` 部署时需要；安装脚本不代装运行依赖 |
| Caddy | 公网反向代理与访问认证 | 可选，配置见下方 WebUI 部分 |

WebUI 前端是**原生 Web Components（Lit 3）**，通过 ESM + import map 运行，运行和修改都
**不需要 Node.js / npm / bundler**。依赖（lit、@material/web、tslib）全部来自仓库内
`webui/vendor/`，运行期不访问 CDN（见 [ADR 0001](adr/0001-webui-frontend-lit.md)）。

### Python 安装与环境一致性

在项目根目录创建独立环境，并将 CLI 和可导入的包安装到同一个环境：

```bash
uv venv --python 3.12
uv pip install --python .venv/bin/python "yt-dlp[default,curl-cffi]"
source .venv/bin/activate
```

另需通过系统包管理器或已有安装提供 Bash、FFmpeg、ffprobe，以及所需的 Chromium、
Node.js、systemd、logrotate。上面的 Python 安装命令不会安装这些系统组件。

README 中的 `uv tool install "yt-dlp[default,curl-cffi]"` 适合安装独立 CLI，
但其依赖位于工具隔离环境，**不保证系统 `python3` 能导入 `curl_cffi`、`yt_dlp`
及 `yt_dlp_ejs`**。仅执行 `uv venv` 也不会安装或激活依赖。
TikTok 检测需要在后端 Python 中导入 `curl_cffi`，YouTube 浏览器路径还会通过
`python3` 启动解算脚本并导入 yt-dlp。因此必须同时确认解释器和子进程 `PATH`。

仓库默认 systemd 单元以 `ubuntu` 用户、`/usr/bin/python3` 运行；激活终端的虚拟环境
不会改变服务环境。用虚拟环境时，**引擎宿主是必须的、WebUI 不是**：

- `livestream-recorderd`（引擎宿主）**必须**用能导入 `curl_cffi` / `yt-dlp`(`yt_dlp_ejs`)
  的解释器——它是构造并运行引擎的进程；
- `livestream-webui` 当前导入链在**导入期不加载** `curl_cffi`（`tiktok_extract` 里是函数内
  延迟导入），所以只做 UI/API 时不需要这些包；想省事也可以让它用同一个 venv。

按需覆盖（`systemctl edit` 生成 drop-in，路径按实际项目位置修改）：

```ini
# sudo systemctl edit livestream-recorderd
[Service]
ExecStart=
ExecStart=/home/ubuntu/tiktok/.venv/bin/python /home/ubuntu/tiktok/webui/recorderd.py
Environment=PATH=/home/ubuntu/tiktok/.venv/bin:/home/ubuntu/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

改的是单元/drop-in → 先 `sudo systemctl daemon-reload` 再 `systemctl restart livestream-recorderd`
（重启引擎宿主会中断并恢复录制）；只改 `/etc/default/livestream-webui` 里的环境变量则
不需要 `daemon-reload`，直接重启对应服务即可。
独立运行 Bilibili 推流脚本或 user 服务时，也需为其 `python3` 与 `yt-dlp` 设置同样的环境。
共享浏览器服务本身只使用 Python 标准库，无需为它安装这些 Python 包。

在激活后的环境中检查；对于 systemd 部署，应改用服务实际的解释器及 PATH 验证：

```bash
command -v python3 yt-dlp ffmpeg ffprobe
python3 --version
yt-dlp --version
ffmpeg -version
ffprobe -version
python3 -c 'import sys, curl_cffi, yt_dlp; print(sys.executable); print(curl_cffi.__file__); print(yt_dlp.__file__)'
# YouTube 浏览器路径另外检查：
node --version
node -e 'console.log(typeof fetch, typeof WebSocket)'  # 均应为 function
python3 -c 'import yt_dlp_ejs; print(yt_dlp_ejs.__file__)'
```

直播源抓取失败时，先在实际运行环境更新 yt-dlp 及匹配依赖：

```bash
uv pip install --python .venv/bin/python --upgrade "yt-dlp[default,curl-cffi]"
# 若需要预发布版本，在上面的命令中增加 --pre。
```

### Chromium 路径与浏览器服务

TikTok 的 `scripts/dlr/browserd.py` 按以下顺序选择可执行文件：

1. 环境变量 `TIKTOK_BROWSERD_CHROME`；设置后只使用该路径，路径不存在则失败，不再回退。
2. 固定路径 `/opt/browser-desktop/chromium/chrome`。
3. 在 `PATH` 中按顺序查找 `google-chrome`、`google-chrome-stable`、`chromium`、
   `chromium-browser`；优先选择非 Snap 版本，只有 Snap 候选时仍尝试使用它。

被选中的路径必须能由服务用户执行。代码只做路径存在性/候选查找，浏览器能否实际启动
还取决于执行权限及系统共享库。`systemd/install.sh` 不负责下载或安装 Chromium。

| 配置项 | 默认值 | 作用 |
|---|---|---|
| `TIKTOK_BROWSERD_CHROME` | 未设置，按上述顺序查找 | TikTok 共享服务使用的浏览器可执行文件 |
| `TIKTOK_BROWSERD_URL` | `http://127.0.0.1:9555` | TikTok 渲染服务 HTTP 地址 |
| `TIKTOK_BROWSERD_PROFILE` | `~/.cache/tiktok-browserd/profile` | 共享浏览器的常驻用户数据目录，`~` 属于服务运行用户 |
| `YOUTUBE_BROWSER_CDP` | `http://127.0.0.1:9222` | YouTube 连接的已有浏览器 CDP 地址 |

TikTok 服务通过 `--remote-debugging-pipe` 管理自己启动的浏览器；9555 是渲染服务
HTTP 端口。YouTube 连接的是另一条 CDP 接口，需要事先运行开启远程调试、具有所需
登录态的浏览器；它不会使用 `TIKTOK_BROWSERD_CHROME` 启动浏览器。

自定义 TikTok 浏览器路径时，执行 `sudo systemctl edit tiktok-browserd`，填写：

```ini
[Service]
Environment=TIKTOK_BROWSERD_CHROME=/absolute/path/to/chrome
```

再执行 `sudo systemctl daemon-reload` 和 `sudo systemctl restart tiktok-browserd`。
该单元没有读取 `/etc/default/livestream-webui`，因此仅修改 WebUI 的环境文件不会
改变 browserd 的浏览器路径。`YOUTUBE_BROWSER_CDP` 则应配置在 WebUI 或录制进程的环境中。

验证浏览器及两个接口（第二个接口仅在使用 YouTube 浏览器路径时需要）：

```bash
/opt/browser-desktop/chromium/chrome --version  # 使用自定义路径时替换
systemctl status tiktok-browserd --no-pager
curl -fsS http://127.0.0.1:9555/health           # 期望输出 ok
curl -fsS http://127.0.0.1:9222/json/version    # 期望输出浏览器 CDP 信息
```

### 外部平台与登录凭据

录制依赖对应直播平台的网页/API 及其媒体 CDN 可访问；Bilibili 开播、投稿与转推
还需要访问 Bilibili API、上传服务及 RTMP 推流端点。项目无需单独购买第三方解析 API。
部分直播需要 Cookie 或登录态：TikTok 默认读取项目根 `cookies.txt`，其他平台可使用
任务的 Cookie 文件；SOOP 还支持 `SOOP_USERNAME` / `SOOP_PASSWORD` 或 netrc。
Bilibili 需要登录会话与推流凭据。具体操作见[使用说明](usage.md)和
[Bilibili 文档](../bili/README.md)，凭据文件不要提交仓库。

## 新版 ffmpeg（TikTok 原画，可选）

TikTok 原画档（origin）通常只有 H.265，放在 FLV 里用的是私有 codec id 12。
系统自带的 ffmpeg 6.1 解不了它（只剩音频），所以默认只拉 H.264 档——多是 TikTok
自己转码的 hd 档（720p 约 1 Mbps）。本机已切换到 BtbN 的 **9.0 稳定分支构建**，
2026-10-16 核对版本为 `n9.0.2-28-g669f5ab083-20261015`，安装位置为
`/home/ubuntu/.local/opt/ffmpeg/bin/ffmpeg`。旧 master 开发版已移除。

以下命令安装同一稳定分支（`n9.0` 包）；下载地址中的 `latest` 表示该分支最新构建，
具体版本可能随时间变化：

```bash
mkdir -p ~/.local/opt && cd /tmp
curl -LO https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-n9.0-latest-linuxarm64-gpl-9.0.tar.xz
tar xf ffmpeg-n9.0-latest-linuxarm64-gpl-9.0.tar.xz
rm -rf ~/.local/opt/ffmpeg && mv ffmpeg-n9.0-latest-linuxarm64-gpl-9.0 ~/.local/opt/ffmpeg
~/.local/opt/ffmpeg/bin/ffmpeg -version | head -1
```

x86_64 机器把 `linuxarm64` 换成 `linux64`。系统 ffmpeg 不受影响。

程序按路径选择 FFmpeg，不比较版本号：录制使用 `DLR_FFMPEG` → 本地固定路径
`~/.local/opt/ffmpeg/bin/ffmpeg`（可执行时）→ `PATH` 中的 `ffmpeg`；TikTok 转推使用
`BILI_FFMPEG` → 同一本地路径（可执行时）→ `PATH` 中的 `ffmpeg`。
文件轮播、SOOP/Twitch 转推直接使用 `PATH` 中的 `ffmpeg`。系统 `/usr/bin/ffmpeg`
仍可与本地稳定版共存；仅安装本地版本不会替换系统命令。

本地版本用于新启动的 FFmpeg 进程，已经运行的进程需要重新启动才能使用替换后的文件：

| 链路 | 变化 |
|---|---|
| 本地录制（`scripts/dlr/`） | 改用新版 ffmpeg；TikTok 按 origin → uhd → hd → sd → ld 挑档（受画质设置上限约束），yt-dlp 挪到取流链最后（它常只给 hd 档） |
| B 站转推（`bili/push.sh`） | 改用新版 ffmpeg 拉原画，缩到 ≤720 宽后编码推流 |
| 文件轮播（`bili/replay.sh`） | 列表里有 H.265 文件时自动改为 `--encode`（FLV 推流只收 H.264） |

实测（2026-10-15，720p 原画约 2.7 Mbps H.265）：

- 录制文件按源码率原样保存，每小时约 1.2 GB（hd 档约 0.48 GB）。
- 转推比拉 hd 档 PSNR 高约 1.9–2.4 dB；ffmpeg 约占 70–105% 单核（视源分辨率与画面复杂度，hd 档约 50%）。
- 录出的 MP4 视频为 H.265（`hev1`）。部分浏览器/播放器不支持 H.265，预览没画面时用 VLC/mpv。

H.265 开关也依赖路径：录制仅在最终选择的路径等于本地固定路径时启用；TikTok 转推
仅在未设置 `BILI_FFMPEG`、自动选中本地版本时启用。显式指定其他路径，即使版本较新，
也不会自动放开 H.265。

用的是 9.0 稳定分支（2026-10-16 实测 9.0.2 可解 TikTok H.265 FLV，与 master 构建结果一致）。
不会自动更新；想拿 9.0.x 修复版时重复上面的安装步骤。换大版本前先用 `ffprobe` 对一路在播的
原画 URL 确认仍能识别出 `hevc` 视频流。

## Bilibili 推流

见本仓库 [`bili/README.md`](../bili/README.md)：命令行开播/推流/轮播、systemd user
单元（`bili-live` / `bili-replay` / `bili-webui`）与推流码管理（`~/.config/bili/`）。
安装：`bash bili/systemd/install.sh`。

`~/.config/bili/` 下由管理页维护的配置（均 600）：

| 文件 | 键 | 含义 |
|---|---|---|
| `live.env` | `TARGET` | **固定的**推流目标 TikTok 主播 |
| `replay.env` | `REPLAY_ARGS` | 文件轮播的路径与 `--encode` |
| `auto.env` | `AUTO` / `EPOCH` | 值守：开播自动起推流、关播自动停推流（1 开 / 0 关）；`EPOCH` 每次开值守刷新，`bili-monitord` 见到变化即清零连续下播计数 |
| `push.env` | `BILIBILI_PUSH_URL` / `BILIBILI_PUSH_CODE` | 当前推流码，每次开播刷新 |
| `monitord.json` | — | 值守快照，**只由 `bili-monitord` 写**，管理页只读 |
| `control.lock` | — | 用户操作与自动接管互斥的 flock 锁文件 |

手动等价操作（会绕过管理页的值守判断）：

```bash
echo 'TARGET=some_user' > ~/.config/bili/live.env   # 换固定目标
systemctl --user restart bili-live.service          # 让 push.sh 读到新目标
echo 'AUTO=1' > ~/.config/bili/auto.env             # 手动开值守
```


## WebUI

安装脚本会创建权限为 `600` 的 `/etc/default/livestream-webui`：

```text
LIVE_WEBUI_HOST=127.0.0.1
LIVE_WEBUI_PORT=8766
RECORDINGS_DIR=/home/ubuntu/tiktok/recordings
```

默认服务以 `ubuntu`、`/usr/bin/python3` 运行，单元内已将 `~/.local/bin` 加入 `PATH`；
Python 包仍需由实际解释器可导入，使用虚拟环境时按上方「Python 安装与环境一致性」设置
覆盖项（旧版 `record.sh` 包装仅保留给命令行）。该环境文件由 `livestream-webui.service`
与 `livestream-recorderd.service` **共用**：`LIVE_WEBUI_HOST/PORT` 只对 WebUI 生效，
`RECORDINGS_DIR` 两者都需要；控制面 socket 路径可选（默认 `<STATE_DIR>/run/recorderd.sock`）：

```text
RECORDERD_SOCKET=/home/ubuntu/tiktok/state/run/recorderd.sock
```

重启语义：`systemctl restart livestream-webui` 不影响录制；`systemctl restart
livestream-recorderd` 会优雅收尾当前分段并按任务目录恢复全部未暂停任务（见
[ADR 0002](adr/0002-recorderd-split.md)）。

后端不校验令牌，因此必须保持监听回环地址，并仅在内网、VPN 或带访问控制的反向代理后使用。改配置后按影响面重启：

```bash
# 只改 LIVE_WEBUI_HOST / LIVE_WEBUI_PORT → 仅 WebUI（不影响录制）
sudo systemctl restart livestream-webui

# 改 RECORDINGS_DIR / RECORDERD_SOCKET → 两个服务都要（引擎与 UI 必须看同一份目录/同一个 socket）
sudo systemctl restart livestream-recorderd   # 会优雅收尾当前分段并按任务目录恢复
sudo systemctl restart livestream-webui
```

环境变量（`EnvironmentFile=`）在每次启动时读取，因此改 `/etc/default/livestream-webui`
不需要 `daemon-reload`；只有改单元文件或 drop-in 才需要。

### Caddy 反向代理

真实的 Caddy 配置由服务器上的 `/etc/caddy/Caddyfile` 管理，本仓库不会安装或覆盖它。下面是仅代理 WebUI 的最小示例；公开部署时不要删除 `basicauth`：

```caddyfile
example.com {
    redir /tiktok /tiktok/ 308

    handle_path /tiktok/* {
        basicauth {
            admin <PASSWORD_HASH>
        }
        reverse_proxy 127.0.0.1:8766
    }
}
```

使用 Caddy 生成密码哈希并替换 `<PASSWORD_HASH>`，不要把明文密码写入配置或仓库：

```bash
caddy hash-password --plaintext '替换为高强度密码'
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

如果在站点级配置 `basicauth`，它会保护该站点的全部子路径；放在 `handle_path /tiktok/*` 内则只保护 WebUI。

`RECORDINGS_DIR` 可以指向仓库外的磁盘。使用自定义目录时，需要先创建目录，并同步调整 systemd unit 的 `ReadWritePaths`，否则 `ProtectSystem=strict` 会阻止服务写入：

```bash
sudo install -d -m 755 /data/live
```

不要把 Cookie 或 Bilibili 推流码提交到仓库。

## Cookie 文件

Cookie 文件使用 Netscape 格式，从本机已登录的浏览器导出后存到项目根
（`cookies.txt` / `soop-cookies.txt`，均已被 `.gitignore` 排除）：

```text
# 项目根 cookies.txt（TikTok）或 soop-cookies.txt（SOOP）
```

文件应仅当前用户可读写（`chmod 600`）。不要提交、分享或写入日志。
各平台 `record.sh` 检测到默认文件存在时会自动附带；也可用 `--cookies FILE` 显式指定。

## SOOP 凭据

SOOP（Sooplive）的会员订阅直播需要登录才能取流。引擎会自动携带以下任一凭据：

- **netrc**：在运行用户主目录放 `~/.netrc`（权限 `600`），内容为
  `machine afreecatv login <SOOP用户ID> password <SOOP密码>`，引擎自动加 `--netrc`。
- **环境变量**：`SOOP_USERNAME` / `SOOP_PASSWORD`，引擎自动带 `--username`/`--password`。
- **Cookie**：登录后的 Netscape 会话 Cookie。存为项目根 `soop-cookies.txt`
  （已 gitignore）时命令行 `platforms/soop/record.sh` 与 WebUI 任务都会自动附带 `--cookies`；
  也可显式 `bash platforms/soop/record.sh <id> --cookies file`。

凭据不要提交仓库、写入日志或日志系统。会员直播通常还需对主播订阅/付费才能观看。
