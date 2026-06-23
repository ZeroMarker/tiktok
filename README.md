# Live Stream Toolkit

用于无人值守录制直播，或将直播源转推到 Bilibili。

当前脚本覆盖：

- TikTok 录制、本地分段保存、转推 Bilibili
- 抖音录制、本地分段保存
- SOOP 录制、本地分段保存、转推 Bilibili
- Twitch 转推 Bilibili
- YouTube 转推 Bilibili

## 依赖

基础依赖：

- Bash 或 PowerShell
- Python 3
- `ffmpeg`
- `yt-dlp`
- `uv`，用于创建 Python 环境和安装工具

推荐初始化：

```bash
uv venv
uv tool install "yt-dlp[default,curl-cffi]"
```

确认命令可用：

```bash
yt-dlp --version
ffmpeg -version
python --version
```

如果直播源抓取失败，优先更新 `yt-dlp`：

```bash
yt-dlp --update-to nightly
```

## Bilibili 推流配置

转推脚本会从 `~/.bashrc` 读取 Bilibili 推流地址和密钥，并拼成完整 RTMP 地址。

在 `~/.bashrc` 中配置：

```bash
export BILIBILI_PUSH_URL="rtmp://example/live-bvc/"
export BILIBILI_PUSH_CODE="your-stream-key"
```

修改后重新加载：

```bash
source ~/.bashrc
```

## 目录说明

```text
.
├── bili/       # 转推 Bilibili 相关脚本
├── douyin/     # 抖音录制脚本和 DouyinLiveRecorder 依赖
├── soop/       # SOOP 录制脚本
├── tk/         # TikTok 录制脚本
├── twitch/     # Twitch 转推 Bilibili 脚本
├── start.sh    # TikTok 直播源测试命令
└── yt.sh       # YouTube 转推 Bilibili 脚本
```

录制脚本会按账号创建输出目录，并每 10 分钟生成一个 MP4 文件。日志默认写入对应目录下的 `logs/`。

## 本地录制

### TikTok

Linux / macOS：

```bash
bash tk/record.sh <tiktok_username>
```

示例：

```bash
bash tk/record.sh kobiritukii
```

PowerShell：

```powershell
. .\tk\record.ps1
Record-TikTok -Username <tiktok_username>
```

### 抖音

抖音录制依赖 `douyin/DouyinLiveRecorder`。可传入 `web_rid`、抖音号或完整直播间 URL。

Linux / macOS：

```bash
bash douyin/record.sh <web_rid|抖音号|完整URL>
```

示例：

```bash
bash douyin/record.sh 1930162853
bash douyin/record.sh @zhangsan
bash douyin/record.sh https://live.douyin.com/1234567890
```

PowerShell：

```powershell
.\douyin\record.ps1 <web_rid|抖音号|完整URL>
```

### SOOP

可传入 SOOP 用户名或直播链接。

```bash
bash soop/record.sh <soop_username|SOOP直播链接>
```

示例：

```bash
bash soop/record.sh playerid
bash soop/record.sh https://play.sooplive.co.kr/playerid
```

## 转推到 Bilibili

转推前请先完成 `BILIBILI_PUSH_URL` 和 `BILIBILI_PUSH_CODE` 配置。

### TikTok 转推

```bash
bash bili/push.sh <tiktok_username>
```

示例：

```bash
bash bili/push.sh kobiritukii
```

### SOOP 转推

```bash
bash bili/soop.sh <SOOP直播间URL>
```

示例：

```bash
bash bili/soop.sh https://play.sooplive.co.kr/playerid
```

### Twitch 转推

```bash
bash twitch/twitch.sh <twitch_username|完整URL>
```

示例：

```bash
bash twitch/twitch.sh shroud
bash twitch/twitch.sh https://www.twitch.tv/shroud
```

### YouTube 转推

可传入频道 handle 或完整直播链接。

```bash
bash yt.sh <YouTube频道handle|直播链接>
```

示例：

```bash
bash yt.sh @PewDiePie
bash yt.sh https://www.youtube.com/@MrBeast/live
```

## 测试直播源

可以先用 `yt-dlp --get-url` 验证直播源是否能抓到：

```bash
yt-dlp "https://www.tiktok.com/@kobiritukii/live" --get-url
```

抖音可以使用项目内脚本测试：

```bash
python douyin/get_stream.py 1930162853
python douyin/get_stream.py 1930162853 --get-url
python douyin/get_stream.py 1930162853 --get-nickname
```

## 常见问题

**抓不到直播源**

- 确认主播正在直播。
- 更新 `yt-dlp` 到最新版本。
- 检查地区限制、Cookie、登录态或平台风控。
- 抖音录制需要确认 `douyin/DouyinLiveRecorder` 目录存在且依赖可导入。

**Bilibili 没有画面或推流失败**

- 检查 `BILIBILI_PUSH_URL` 和 `BILIBILI_PUSH_CODE` 是否正确。
- 确认 Bilibili 直播后台已经开启推流。
- 查看 `logs/` 下对应日期的 ffmpeg 日志。

**录制文件没有生成**

- 确认 `ffmpeg` 可执行。
- 确认当前目录有写入权限。
- 查看脚本输出目录和 `logs/`。

## 停止任务

前台运行时按 `Ctrl+C` 停止。后台运行时使用 `ps` 找到脚本或 `ffmpeg` 进程后 `kill`。
