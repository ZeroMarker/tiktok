# 配置

## 基础依赖

需要以下命令可用：

- Bash 或 PowerShell
- Python 3
- `ffmpeg`
- `yt-dlp`
- `uv`

推荐初始化：

```bash
uv venv
uv tool install "yt-dlp[default,curl-cffi]"
```

确认依赖：

```bash
yt-dlp --version
ffmpeg -version
python --version
```

脚本启动时会检查对应依赖；缺少命令时会直接退出并给出错误，而不会进入无限重试。

直播源抓取失败时，优先更新 `yt-dlp`：

```bash
yt-dlp --update-to nightly
```

## 新版 ffmpeg（TikTok 原画，可选）

TikTok 原画档（origin）通常只有 H.265，放在 FLV 里用的是私有 codec id 12。
系统自带的 ffmpeg 6.1 解不了它（只剩音频），所以默认只拉 H.264 档——多是 TikTok
自己转码的 hd 档（720p 约 1 Mbps）。装一份新版 ffmpeg 即可拉原画：

```bash
mkdir -p ~/.local/opt && cd /tmp
curl -LO https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz
tar xf ffmpeg-master-latest-linuxarm64-gpl.tar.xz
rm -rf ~/.local/opt/ffmpeg && mv ffmpeg-master-latest-linuxarm64-gpl ~/.local/opt/ffmpeg
~/.local/opt/ffmpeg/bin/ffmpeg -version | head -1
```

x86_64 机器把 `linuxarm64` 换成 `linux64`。系统 ffmpeg 不受影响。

`~/.local/opt/ffmpeg/bin/ffmpeg` 存在时自动生效，无需改配置（新起的录制/推流进程才会用上，
已在跑的需重启）：

| 链路 | 变化 |
|---|---|
| 本地录制（`scripts/dlr/`） | 改用新版 ffmpeg；TikTok 按 origin → uhd → hd → sd → ld 挑档（受画质设置上限约束），yt-dlp 挪到取流链最后（它常只给 hd 档） |
| B 站转推（`bili/push.sh`） | 改用新版 ffmpeg 拉原画，缩到 ≤720 宽后编码推流 |
| 文件轮播（`bili/replay.sh`） | 列表里有 H.265 文件时自动改为 `--encode`（FLV 推流只收 H.264） |

实测（2026-10-15，720p 原画约 2.7 Mbps H.265）：

- 录制文件按源码率原样保存，每小时约 1.2 GB（hd 档约 0.48 GB）。
- 转推比拉 hd 档 PSNR 高约 2.4 dB；ffmpeg 约占 70% 单核（hd 档约 50%）。
- 录出的 MP4 视频为 H.265（`hev1`）。部分浏览器/播放器不支持 H.265，预览没画面时用 VLC/mpv。

覆盖路径：录制用 `DLR_FFMPEG`，转推用 `BILI_FFMPEG`。显式指定时**不会**放开 H.265 档
（无法确认该 ffmpeg 能解），仍只拉 H.264。

新版是 master 每日构建，不会自动更新；想更新时重复上面的安装步骤。

## Bilibili 推流

见本仓库 [`bili/README.md`](../bili/README.md)：命令行开播/推流/轮播、systemd user
单元（`bili-live` / `bili-replay` / `bili-webui`）与推流码管理（`~/.config/bili/`）。
安装：`bash bili/systemd/install.sh`。

`~/.config/bili/` 下由管理页维护的配置（均 600）：

| 文件 | 键 | 含义 |
|---|---|---|
| `live.env` | `TARGET` | **固定的**推流目标 TikTok 主播 |
| `replay.env` | `REPLAY_ARGS` | 文件轮播的路径与 `--encode` |
| `auto.env` | `AUTO` | 值守：开播自动起推流、关播自动停推流（1 开 / 0 关） |
| `push.env` | `BILIBILI_PUSH_URL` / `BILIBILI_PUSH_CODE` | 当前推流码，每次开播刷新 |

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

服务以 `ubuntu` 运行（单进程模型：录制引擎线程与 WebUI 同进程），依赖
（yt-dlp / curl_cffi）取自其 `~/.local`，单元内已显式补齐 `PATH`（旧版靠
`record.sh` 包装桥接，包装仅保留给命令行）。

后端不校验令牌，因此必须保持监听回环地址，并仅在内网、VPN 或带访问控制的反向代理后使用。修改配置后执行：

```bash
sudo systemctl restart livestream-webui
```

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
