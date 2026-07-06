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

## TikTok 个别账号录制失败

个别账号可能出现“页面能看，但 `yt-dlp` 判断未开播”的情况。通常优先验证 Cookie、浏览器指纹模拟和 verbose 日志；确认某个参数稳定有效后，再把它合入对应录制脚本。
