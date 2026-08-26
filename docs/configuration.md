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

## Bilibili 推流

转推脚本从 `~/.bashrc` 读取 Bilibili 推流地址和密钥：

```bash
export BILIBILI_PUSH_URL="rtmp://example/live-bvc/"
export BILIBILI_PUSH_CODE="your-stream-key"
```

修改后重新加载：

```bash
source ~/.bashrc
```

推流脚本会拼接：

```text
${BILIBILI_PUSH_URL}${BILIBILI_PUSH_CODE}
```

如果任一变量为空，转推脚本会在启动 ffmpeg 前退出。脚本不会在终端输出完整推流地址、推流码或直播源签名 URL。

## WebUI

安装脚本会创建权限为 `600` 的 `/etc/default/livestream-webui`：

```text
LIVE_WEBUI_HOST=127.0.0.1
LIVE_WEBUI_PORT=8766
RECORDINGS_DIR=/root/tiktok/recordings
```

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

## 抖音子模块

抖音录制依赖 `douyin/DouyinLiveRecorder`：

```bash
git submodule update --init --recursive
```

如果 Python 无法导入依赖，先确认该目录存在并且子模块已拉取完成。
抖音录制入口也会在启动时检查子模块，并提示上述初始化命令。

## 抖音 Cookie

Cookie 文件使用 Netscape 格式。可以用项目脚本从本机已登录的浏览器导出：

```bash
bash douyin/import_cookies.sh chrome ./douyin-cookies.txt
```

导出文件会自动设置为仅当前用户可读写，并已被 `.gitignore` 排除。不要提交、分享或写入日志。

## SOOP 凭据

SOOP（Sooplive）的会员订阅直播需要登录才能取流。引擎会自动携带以下任一凭据：

- **netrc**：在运行用户主目录放 `~/.netrc`（权限 `600`），内容为
  `machine afreecatv login <SOOP用户ID> password <SOOP密码>`，引擎自动加 `--netrc`。
- **环境变量**：`SOOP_USERNAME` / `SOOP_PASSWORD`，引擎自动带 `--username`/`--password`。
- **Cookie**：登录后的 Netscape 会话 Cookie，`bash soop/record.sh <id> --cookies file`。

凭据不要提交仓库、写入日志或日志系统。会员直播通常还需对主播订阅/付费才能观看。
