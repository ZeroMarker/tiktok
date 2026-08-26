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

## SOOP（Sooplive）订阅直播需要登录

**现象**：`recordings/soop/<频道id>/` 一直为空，日志反复输出「直播未开启 / 抓取失败」，
但浏览器里主播明明在播。

**根因**：该频道是**会员订阅直播**（SOOP live API 返回 `RESULT=-6`）。yt-dlp 的 soop
提取器要求登录凭据才能取流，未登录时直接报：

```text
This channel is streaming for subscribers only. Use --username and --password,
--netrc-cmd, or --netrc (afreecatv) to provide account credentials
```

引擎已把该真实错误打印到日志（不再误报「未开播」）。取流命令应能看到同样的原因：

```bash
yt-dlp --no-warnings -f best --get-url "https://play.sooplive.co.kr/<频道id>"
```

**解决**：提供 SOOP 账号凭据（三选一），引擎会自动携带：

1. **netrc（推荐）**——在运行用户主目录放 `~/.netrc`（权限 `600`）：
   ```text
   machine afreecatv login <SOOP用户ID> password <SOOP密码>
   ```
   然后直接 `bash soop/record.sh <频道id>`，引擎自动加 `--netrc`。

2. **环境变量**——设置后启动引擎，自动带 `--username`/`--password`：
   ```bash
   export SOOP_USERNAME='<SOOP用户ID>'
   export SOOP_PASSWORD='<SOOP密码>'
   bash soop/record.sh <频道id>
   ```

3. **登录 Cookie**——把登录后的 Netscape 会话 Cookie 存为 `soop-cookies.txt`
   （项目根目录，已 gitignore），`soop/record.sh` 检测到会自动附带 `--cookies`：
   ```bash
   # 存好 soop-cookies.txt 后直接录制即可
   bash soop/record.sh <频道id>
   ```

> 注意：会员直播通常还需对主播**订阅/付费**才能观看；仅有普通账号（未订阅该主播）
> 时可能仍无法取流。凭据不要提交仓库。

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

若 yt-dlp 也持续失败，优先排查是否**需要登录 Cookie**：

```bash
# 提供 Netscape 登录 Cookie 后，yt-dlp 常能直接抓到流
yt-dlp --impersonate chrome --cookies cookies.txt \
  -f "b[ext=flv]" --get-url "https://www.tiktok.com/@<user>/live"
```

`tk/record.sh` 会自动检测项目根 `cookies.txt` 并携带；详见
[使用说明](usage.md) 的“TikTok 登录 Cookie”。历史案例（emma_kusunoki 等）见
[tk/error.md](../tk/error.md) 与 [TikTok 录制排障](tiktok-live-recording.md)。

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
