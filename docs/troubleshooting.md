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
bash platforms/tiktok/record.sh <tiktok_username>
yt-dlp -v "https://www.tiktok.com/@<tiktok_username>/live"
yt-dlp --cookies-from-browser chrome "https://www.tiktok.com/@<tiktok_username>/live"
yt-dlp --impersonate chrome "https://www.tiktok.com/@<tiktok_username>/live"
yt-dlp --xff US "https://www.tiktok.com/@<tiktok_username>/live"
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
   然后直接 `bash platforms/soop/record.sh <频道id>`，引擎自动加 `--netrc`。

2. **环境变量**——设置后启动引擎，自动带 `--username`/`--password`：
   ```bash
   export SOOP_USERNAME='<SOOP用户ID>'
   export SOOP_PASSWORD='<SOOP密码>'
   bash platforms/soop/record.sh <频道id>
   ```

3. **登录 Cookie**——把登录后的 Netscape 会话 Cookie 存为 `soop-cookies.txt`
   （项目根目录，已 gitignore），`platforms/soop/record.sh` 检测到会自动附带 `--cookies`：
   ```bash
   # 存好 soop-cookies.txt 后直接录制即可
   bash platforms/soop/record.sh <频道id>
   ```

> 注意：会员直播通常还需对主播**订阅/付费**才能观看；仅有普通账号（未订阅该主播）
> 时可能仍无法取流。凭据不要提交仓库。

## Bilibili 没有画面或推流失败

检查项：

- `BILIBILI_PUSH_URL` 和 `BILIBILI_PUSH_CODE` 是否正确。
- Bilibili 直播后台是否已经开启推流。
- `ffmpeg` 日志里是否有编码、网络或 RTMP 鉴权错误。
- 推流码是否过期或被重置。

## Bilibili 推流音画不同步

症状：B 站直播间里声音和画面对不上，且**偏差随时间不断增大**，不会自愈。

原因（2026-09-28 修复）：推流命令曾用 `setpts=N/FRAME_RATE/TB` 重建视频时间戳。
这个表达式有两个问题：

1. 它用**滤镜的帧计数器 `N`** 和**容器里声明的 `r_frame_rate`**，而不是源流的真实
   时间轴。TikTok 源是真 VFR——实测一条流前 80 s 是 25 fps，之后掉到 15 fps 到底，
   而 `r_frame_rate` 始终写 25。`setpts` 按 25 打戳就把 240 s 的视频压进 181 s。
2. 源流降帧率重起 GOP、或解码中断时，ffmpeg 会重新初始化滤镜图，`N` 归零，
   `setpts` 算出的时间戳**当场倒回 0**，而音频继续往前走。偏差从此永久存在。

音频侧的 `aresample` 只对音频自己的时间戳做补偿，ffmpeg 没有跨流同步机制，
所以两条时间轴一旦分开就只会越差越远。

修复：改用 `-vf fps=N`（按输入真实时间戳做 CFR 转换，保留真实时长，滤镜图
重初始化也不会回卷），音频侧补 `first_pts=0` 把起点钉到 0。`bili/push.sh`（`fps=30`）、
`bili/replay.sh`（`fps=25`）、`platforms/twitch/twitch.sh`（`fps=30`）均已修正。

自查方法——比较推流产物里两条流的时间轴终点，差值就是当前音画偏差：

```bash
ffprobe -v error -select_streams v -show_entries packet=pts_time -of csv=p=0 out.flv | tail -1
ffprobe -v error -select_streams a -show_entries packet=pts_time -of csv=p=0 out.flv | tail -1
```

两个数应当只差一帧以内（30 fps 约 0.03 s，25 fps 约 0.04 s）。若视频终点远早于音频
终点，就是时间轴被压缩了。若要长期监控偏差是否累积，在多个时间点比较两者的进度比例
即可。

注意：ffmpeg progress 里的 `frame=` 与 `time*帧率` 会**恒定差几帧**（约 0.2~0.3 s），
这是计数口径差异、不是音画偏差。判据是「差值是否随时间增长」，不要看它是否等于 0。

完整定位过程与离线对照实验见
[归档：B 站推流音画不同步](archive/bili-push-av-sync.md)。

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
bash platforms/tiktok/record.sh <tiktok_username>
```

若 yt-dlp 也持续失败，优先排查是否**需要登录 Cookie**：

```bash
# 提供 Netscape 登录 Cookie 后，yt-dlp 常能直接抓到流
yt-dlp --impersonate chrome --cookies cookies.txt \
  -f "b[ext=flv]" --get-url "https://www.tiktok.com/@<user>/live"
```

`platforms/tiktok/record.sh` 会自动检测项目根 `cookies.txt` 并携带；详见
[使用说明](usage.md) 的“TikTok 登录 Cookie”。历史案例（emma_kusunoki 等）见
[归档：tiktok-error](archive/tiktok-error.md) 与
[归档：TikTok 录制排障](archive/tiktok-live-recording.md)。

### TikTok 未获取到流与浏览器渲染服务

“未获取到流”首先不等于程序故障。若主播已经下播，`yt-dlp`、Web API 和浏览器兜底
都可能没有流地址；正式入口会按间隔继续轮询。先查看任务日志（WebUI 日志面板，或）：

```bash
less recordings/logs/tiktok/engine_livestream-rec-tiktok-<频道>.log
# 或从服务 stdout（带 [平台:频道] 前缀）过滤：
journalctl -u livestream-webui -n 200 --no-pager | grep tiktok
```

重点区分以下两种情况：

- `所有 API 检测均未发现直播`：通常是未开播，也可能是地区/IP、登录态或反爬限制。
- `浏览器兜底失败 ... timed out`：TikTok 页面或 WAF 在规定时间内没有返回；如果主播
  确实正在直播，再单独验证 `yt-dlp`、Cookie 和网络出口。

**检测顺序**（`scripts/dlr/adapters/tiktok.py`）：每轮必跑一次进程内轻量检测
（`curl_cffi` 页面 + webcast API，带 Cookie）；连续 3 次轻量检测均未发现直播才进入
「升级轮」，此时跑一次带 Cookie 的 `yt-dlp` 主域探测（日志出现
`[tiktok] 升级轮：yt-dlp 主域兜底探测 ...`）并调用一次浏览器兜底。这样避免每轮冷启动
一个 `yt-dlp` 进程（曾达 ~425 次/小时）。

**浏览器兜底走共享常驻服务**，不是每轮冷启动一个浏览器：TikTok 渲染统一由
`tiktok-browserd.service`（`scripts/dlr/browserd.py`，默认 `127.0.0.1:9555`，
`TIKTOK_BROWSERD_URL` 可覆盖）开标签页完成，服务端复用同一个 Chromium 实例和
**一份常驻 profile**（默认 `~/.cache/tiktok-browserd/profile`，
`TIKTOK_BROWSERD_PROFILE` 可覆盖）。因此旧版本“每轮探测建临时 profile、
结束后回收”的行为已不存在，`/tmp/tiktok-chromium-*` 不再产生。浏览器启动参数仍会
禁用 Vulkan；若系统同时安装了非 Snap 浏览器，代码会优先使用它，以减少 AppArmor
审计噪声。

排障时先确认渲染服务本身活着：

```bash
systemctl status tiktok-browserd --no-pager
curl -fsS http://127.0.0.1:9555/health          # 期望输出 ok
ls ~/.cache/tiktok-browserd/profile             # 常驻 profile，正常应有内容
```

服务不可用时引擎会**自动跳过浏览器兜底**，轻量检测与 `yt-dlp` 路径不受影响——所以
“兜底失败”本身不必然等于录不到流。若 profile 损坏，可在暂停/删除全部 TikTok 任务、
确认无 Chromium 进程后删除该目录并 `sudo systemctl restart tiktok-browserd`
（会重建，不要删除 `~/tiktok` 或 `recordings/`）。

若任务已停止却仍有残留 Chromium 进程或目录持续增加，检查是否有旧版本脚本、手动
启动的 `dlr.py`，或其他服务在调用 Chromium：

```bash
ps -eo pid,ppid,user,etime,args | grep -E 'dlr.py tiktok|chromium.*headless' | grep -v grep
pgrep -af 'browserd|webui/app.py'   # 共享渲染服务与录制主进程（单进程模型，无按频道单元）
```

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
du -sh /home/ubuntu/tiktok/recordings/* 2>/dev/null | sort -h
```

删除录像属于不可恢复操作。先确认录像已备份或不再需要，再按明确的日期、频道和文件路径人工清理；项目不会自动删除录像。
