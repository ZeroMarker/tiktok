# 排障

## 抓不到直播源

先确认主播正在直播，然后更新 `yt-dlp`：

```bash
yt-dlp --update-to nightly
```

常见原因：

- 主播未开播。
- 平台返回验证码或反爬页面。
- 需要登录态或 Cookie。
- 地区限制、IP 限制或设备指纹限制。
- 平台改了直播页结构，`yt-dlp` 解析器暂时失效。

TikTok 可逐项验证：

```bash
bash start.sh <tiktok_username>
yt-dlp -v "https://www.tiktok.com/@<tiktok_username>/live"
yt-dlp --cookies-from-browser chrome "https://www.tiktok.com/@<tiktok_username>/live"
yt-dlp --impersonate chrome "https://www.tiktok.com/@<tiktok_username>/live"
yt-dlp --xff US "https://www.tiktok.com/@<tiktok_username>/live"
```

抖音可用项目内脚本验证：

```bash
python douyin/get_stream.py <web_rid|抖音号|完整URL>
python douyin/get_stream.py <web_rid|抖音号|完整URL> --get-url
python douyin/get_stream.py <web_rid|抖音号|完整URL> --get-nickname
```

## Bilibili 没有画面或推流失败

检查项：

- `BILIBILI_PUSH_URL` 和 `BILIBILI_PUSH_CODE` 是否正确。
- Bilibili 直播后台是否已经开启推流。
- `ffmpeg` 日志里是否有编码、网络或 RTMP 鉴权错误。
- 推流码是否过期或被重置。

## 录制文件没有生成

检查项：

- `ffmpeg` 是否可执行。
- 当前目录是否有写入权限。
- 直播源是否能通过检测命令拿到。
- `logs/` 中是否有当天的 `ffmpeg` 日志。

如果提示 `Option timeout not found`，说明使用了旧脚本或旧参数。当前录制入口统一使用 ffmpeg 的 `-rw_timeout` 参数，请更新仓库后重试。

## TikTok 个别账号录制失败

个别账号可能出现“页面能看，但 Web API 或 `yt-dlp` 判断未开播”的情况。Web API 的 GroupBlock 不等于实际流地址一定不可用，先让正式入口持续轮询：

```bash
bash tk/record.sh <tiktok_username>
```

若 yt-dlp 也持续失败，再验证 Cookie、实际出口地区、浏览器指纹模拟和 verbose 日志。详细历史案例见 [TikTok 录制排障](tiktok-live-recording.md)。

## WebUI 无法启动

检查服务与日志：

```bash
systemctl status livestream-webui --no-pager
journalctl -u livestream-webui -n 100 --no-pager
```

- 修改了 `RECORDINGS_DIR` 后无法写入：确认目录存在，并已加入 systemd unit 的 `ReadWritePaths`。

## 磁盘空间不足

检查录像所在文件系统，而不是只看仓库目录：

```bash
df -h "$(systemctl show livestream-webui -p Environment --value | tr ' ' '\n' | sed -n 's/^RECORDINGS_DIR=//p')"
du -sh /root/tiktok/recordings/* 2>/dev/null | sort -h
```

删除录像属于不可恢复操作。先确认录像已备份或不再需要，再按明确的日期、频道和文件路径人工清理；项目不会自动删除录像。
