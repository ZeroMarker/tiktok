# 使用说明

## 本地录制

### TikTok

Linux / macOS：

```bash
bash tk/record.sh <tiktok_username>
```

这是日常录制的正式入口，会持续轮询直播源（yt-dlp → 多方法兜底），断流后自动重新获取。

#### TikTok 登录 Cookie（部分主播需要）

TikTok 对部分主播（登录限流、风控、或直播需要登录才能看）在无登录 Cookie 时不会返回
直播流——yt-dlp / Web API 都会误报“未开播”，但浏览器里明明在播。

解决办法是提供 Netscape 格式的登录 Cookie，`tk/record.sh` 会自动携带：

```bash
# 将浏览器导出的 Cookie 存为项目根 cookies.txt（已 .gitignore 忽略，勿提交）
cp ~/secrets/tiktok-cookies.txt ./cookies.txt

# 直接复用项目入口即可，record.sh 自动附带 Cookie
bash tk/record.sh <tiktok_username>
```

也可显式指定其他 Cookie 文件：

```bash
bash tk/record.sh <tiktok_username> --cookies /secure/tiktok-cookies.txt
```

> 提示：确保录制服务以能访问 `~/.local`（yt-dlp/curl_cffi）的用户运行；
> 详见 [结构](structure.md) 的“控制面 / 运行用户”。

### 抖音

可传入 `web_rid`、抖音号或完整直播间 URL：

```bash
bash douyin/record.sh <web_rid|抖音号|完整URL>
```

示例：

```bash
bash douyin/record.sh 1930162853
bash douyin/record.sh @zhangsan
bash douyin/record.sh https://live.douyin.com/1234567890
```

### SOOP

可传入 SOOP 用户名或直播链接：

```bash
bash soop/record.sh <soop_username|SOOP直播链接>
```

示例：

```bash
bash soop/record.sh playerid
bash soop/record.sh https://play.sooplive.co.kr/playerid
```

### Kick

```bash
bash kick/record.sh xqc
bash kick/record.sh https://kick.com/xqc
```

### YouTube

```bash
bash youtube/record.sh @PewDiePie
bash youtube/record.sh https://www.youtube.com/watch?v=<video_id>
```

### CHZZK

可传入频道 ID 或完整直播间 URL：

```bash
bash chzzk/record.sh <channel_id>
bash chzzk/record.sh https://chzzk.naver.com/live/<channel_id>
```

以上三个入口默认将视频写入 `./recordings/`，可通过 `RECORDINGS_DIR` 修改根目录：

```bash
RECORDINGS_DIR=/data/live bash kick/record.sh xqc
```

### 抖音 Cookie

从已登录的浏览器导出 Netscape 格式 Cookie：

```bash
bash douyin/import_cookies.sh chrome
```

也可指定浏览器和输出路径：

```bash
bash douyin/import_cookies.sh firefox /secure/douyin-cookies.txt
```

录制或检测时导入：

```bash
bash douyin/record.sh 1930162853 --cookies /secure/douyin-cookies.txt
python douyin/get_stream.py 1930162853 --cookies /secure/douyin-cookies.txt
```

临时使用原始 Cookie 请求头时可传 `--cookie 'name=value; ...'`。该方式可能出现在进程参数和终端历史中，长期运行推荐使用权限为 `600` 的 Cookie 文件。

## 转推到 Bilibili

转推前先完成 `BILIBILI_PUSH_URL` 和 `BILIBILI_PUSH_CODE` 配置。

### TikTok

```bash
bash bili/push.sh <tiktok_username>
```

### SOOP

```bash
bash bili/soop.sh <SOOP直播间URL>
```

### Twitch

```bash
bash twitch/twitch.sh <twitch_username|完整URL>
```

示例：

```bash
bash twitch/twitch.sh shroud
bash twitch/twitch.sh https://www.twitch.tv/shroud
```

### YouTube

可传入频道 handle 或完整直播链接：

```bash
bash yt.sh <YouTube频道handle|直播链接>
```

示例：

```bash
bash yt.sh @PewDiePie
bash yt.sh https://www.youtube.com/@MrBeast/live
```

## 直播源检测

TikTok：

```bash
bash start.sh <tiktok_username|直播URL>
```

抖音：

```bash
python douyin/get_stream.py 1930162853
python douyin/get_stream.py 1930162853 --get-url
python douyin/get_stream.py 1930162853 --get-nickname
```

## 停止任务

前台运行时按 `Ctrl+C` 停止。后台运行时使用 `ps` 找到脚本或 `ffmpeg` 进程后 `kill`。

## WebUI / systemd 管理

安装服务：

```bash
sudo bash systemd/install.sh
```

常用维护命令：

```bash
systemctl status livestream-webui
journalctl -u livestream-webui -f
sudo systemctl restart livestream-webui
```

WebUI 创建的录制任务名称以 `livestream-rec-` 开头，可以直接用 systemd 查看：

```bash
systemctl list-units 'livestream-rec-*.service' --all
journalctl -u '<任务名称>' -f
```

默认仅允许本机连接。通过 SSH 隧道远程访问：

```bash
ssh -L 8765:127.0.0.1:8766 <server>
```

浏览器可打开 `https://20070809.xyz/tiktok/`。域名根路径继续转发其他服务，只有 `/tiktok/` 子路径进入 WebUI。

WebUI 后端没有应用层认证；当前公网入口由站点级 Caddy Basic Auth 保护。不要直接对外开放后端端口。

WebUI 的“最近文件”和磁盘统计均读取 `RECORDINGS_DIR`。修改录像目录后必须重启服务。
WebUI 新建录制时可选择画质（原画/1080p/720p/480p），画质经各平台 `record.sh` 透传给录制引擎，
用于限制检测到的流清晰度；选择“原画”则不设上限。文件列表支持点击“播放”在内嵌播放器中
预览任一录制片段（`/api/file` 支持 HTTP Range 拖动进度）。
WebUI 前端为 Vue 3 + Vite（源码在 `webui/frontend/src`），`webui/index.html` 是单文件构建产物。
改动前端后需重新构建：`cd webui/frontend && npm run build`（构建脚本会把 `dist/index.html` 复制回 `../index.html`）。

DouyinLiveRecorder 管理页面位于 `https://20070809.xyz/douyin/`。

服务器状态监控页面位于 `https://20070809.xyz/sysmon/`。
