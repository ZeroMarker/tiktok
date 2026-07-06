# 使用说明

## 本地录制

### TikTok

Linux / macOS：

```bash
bash tk/record.sh <tiktok_username>
```

PowerShell：

```powershell
. .\tk\record.ps1
Record-TikTok -Username <tiktok_username>
```

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

PowerShell：

```powershell
.\douyin\record.ps1 <web_rid|抖音号|完整URL>
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
