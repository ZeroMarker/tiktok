# 使用说明

## 本地录制

### TikTok

Linux / macOS：

```bash
bash platforms/tiktok/record.sh <tiktok_username>
```

这是日常录制的正式入口，会持续轮询直播源（yt-dlp → 多方法兜底），断流后自动重新获取。

#### TikTok 登录 Cookie（部分主播需要）

TikTok 对部分主播（登录限流、风控、或直播需要登录才能看）在无登录 Cookie 时不会返回
直播流——yt-dlp / Web API 都会误报“未开播”，但浏览器里明明在播。

解决办法是提供 Netscape 格式的登录 Cookie，`platforms/tiktok/record.sh` 会自动携带：

```bash
# 将浏览器导出的 Cookie 存为项目根 cookies.txt（已 .gitignore 忽略，勿提交）
cp ~/secrets/tiktok-cookies.txt ./cookies.txt

# 直接复用项目入口即可，record.sh 自动附带 Cookie
bash platforms/tiktok/record.sh <tiktok_username>
```

也可显式指定其他 Cookie 文件：

```bash
bash platforms/tiktok/record.sh <tiktok_username> --cookies /secure/tiktok-cookies.txt
```

> 提示：确保录制服务以能访问 `~/.local`（yt-dlp/curl_cffi）的用户运行；
> 详见 [结构](structure.md) 的“控制面 / 运行用户”。

### SOOP

可传入 SOOP 用户名或直播链接：

```bash
bash platforms/soop/record.sh <soop_username|SOOP直播链接>
```

示例：

```bash
bash platforms/soop/record.sh playerid
bash platforms/soop/record.sh https://play.sooplive.co.kr/playerid
```

### Kick

```bash
bash platforms/kick/record.sh xqc
bash platforms/kick/record.sh https://kick.com/xqc
```

### YouTube

```bash
bash platforms/youtube/record.sh @PewDiePie
bash platforms/youtube/record.sh https://www.youtube.com/watch?v=<video_id>
```

频道 handle 可带或不带开头的 `@`。如 YouTube 要求登录验证，可用
`--cookies /path/to/youtube-cookies.txt` 传入从已登录浏览器导出的 Netscape
Cookie 文件；WebUI 任务也支持通过 `cookie_file` 参数指定该文件。
服务器上的 browser-desktop Chromium 可作为 YouTube 直播取流兜底
（默认 CDP 地址 `http://127.0.0.1:9222`，可用 `YOUTUBE_BROWSER_CDP` 覆盖）。
引擎会先检查 HLS 媒体分片是否可访问；分片返回 403 时即使直播清单存在也无法录制。

### CHZZK

可传入频道 ID 或完整直播间 URL：

```bash
bash platforms/chzzk/record.sh <channel_id>
bash platforms/chzzk/record.sh https://chzzk.naver.com/live/<channel_id>
```

以上三个入口默认将视频写入 `./recordings/`，可通过 `RECORDINGS_DIR` 修改根目录：

```bash
RECORDINGS_DIR=/data/live bash platforms/kick/record.sh xqc
```

### Cookie

所有平台的 `record.sh` 都接受 `--cookies FILE`（Netscape 格式）显式指定登录态；
TikTok 与 SOOP 另有默认文件（`cookies.txt` / `soop-cookies.txt`），存在时自动附带。
临时使用原始 Cookie 请求头时可传 `--cookie 'name=value; ...'`——该方式可能出现在
进程参数和终端历史中，长期运行推荐使用权限为 `600` 的 Cookie 文件。

## Bilibili：推流与投稿

Bilibili 相关（开播、转推、轮播、值守、质检、稿件投稿）见本仓库
[`bili/`](../bili/README.md)，与录制侧同仓：轮播直接消费本仓库的录制输出
（`recordings/`），`watch.sh` 自动携带本仓库根的 `cookies.txt`。

### 稿件投稿

把录制文件投成 B 站普通稿件（分区投稿，不进直播间）。登录态只有一条来源：
`bili/live.py login` 扫码。登录态按账号分档存在 `~/.config/bili/accounts/`，
推流用 `live` 账号、投稿用 `upload` 账号，互不干扰（详见
[`bili/README.md`](../bili/README.md#登录态来源)）。`--state` 记录每个文件的
`filename`/`cid`，中断可续传：

```bash
python3 bili/live.py login --account upload     # 首次：给投稿账号扫码
python3 bili/live.py accounts                   # 看所有账号与登录态有效期
python3 bili/upload.py status                   # 确认投稿账号登录态
python3 bili/upload.py --state /tmp/s.json push <文件|目录>            # 只传文件
python3 bili/upload.py --state /tmp/s.json post --title "标题" --tid 21 \
    --tag "a,b" --source "来源" --part-title-prefix "标题"            # 提交稿件
```

录播要合成 1 稿多分 P：连续提交约 10 个独立稿件会触发 B 站 `code: 601`
「上传视频过快」。版权按转载投（`--copyright 2` + `--source`）——B 站明确
「录制他人直播不属于自制内容」。详见 [`bili/README.md`](../bili/README.md#稿件投稿uploadpy)。

### Twitch

```bash
bash platforms/twitch/twitch.sh <twitch_username|完整URL>
```

示例：

```bash
bash platforms/twitch/twitch.sh shroud
bash platforms/twitch/twitch.sh https://www.twitch.tv/shroud
```

### YouTube → Bilibili 转推

YouTube 直播源转推到 B 站统一走 `bili/` 的转推链路（见上文「Bilibili：推流与投稿」），
`bash platforms/youtube/record.sh <handle>` 只做本地录制。

## 直播源检测

各平台的检测能力已并入录制引擎与 WebUI 概览页（每个任务的 `live` 字段）：

```bash
bash platforms/tiktok/record.sh <tiktok_username|直播URL>   # 检测 + 录制
```

只想判断能不能取到流、不录制，用 WebUI 概览页看 `直播中` 计数即可。

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

WebUI 创建的录制任务是服务进程内的引擎线程（单进程模型），任务 ID 仍以
`livestream-rec-` 开头。查看整体运行与单频道日志：

```bash
journalctl -u livestream-webui -f                      # 所有频道（带 [平台:频道] 前缀）
less recordings/logs/tiktok/engine_<任务ID>.log        # 单频道引擎日志
```

默认仅允许本机连接。通过 SSH 隧道远程访问：

```bash
ssh -L 8765:127.0.0.1:8766 <server>
```

浏览器可打开 `https://20070809.xyz/tiktok/`。域名根路径继续转发其他服务，只有 `/tiktok/` 子路径进入 WebUI。

WebUI 后端没有应用层认证；当前公网入口由站点级 Caddy Basic Auth 保护。不要直接对外开放后端端口。

WebUI 的“最近文件”和磁盘统计均读取 `RECORDINGS_DIR`。修改录像目录后必须重启服务。
任务卡片提供三种控制：

- **暂停**：请求引擎优雅停止（立即向 ffmpeg 发终止信号收尾当前分段），短 join 最长
  5 秒——引擎若正阻在网络调用（页面抓取超时可达 20 秒）里，接口不挂起，线程转后台
  自行退出；任务**保留在列表中**显示“已暂停”，启动参数（画质、Cookie 等）留在任务
  目录，随时“继续”按原参数重新拉起。暂停期间不占进程、不检测开播。
- **继续**：按任务目录 `state/tasks.json` 里保存的启动参数，在服务进程内重建引擎线程
  （`WEBUI_STATE_DIR` 可覆盖路径；服务单元已放行 `state/` 的写权限）。
- **开机恢复**：WebUI 启动时自动把目录中所有未暂停的任务恢复为引擎线程；暂停任务保持
  暂停。因此应通过“删除”永久移除任务——重启服务不会清除任务目录里的记录。
- **删除**：停止该任务（若在运行）并移除任务记录，**不会删除已录制的文件**；录像仍在
  “录制文件”页面可单独删除，删除暂停中的任务同样只改目录。

点击后卡片立刻显示状态并禁用该行操作（读取的是进程内实时状态，刷新不丢）；引擎异常
退出会按 10 秒退避自动重启并计入“重启次数”（等价旧版 Restart=on-failure）。日志页读取
该任务的引擎日志文件（尾部最多 5000 行）。旧版“每频道一个 systemd 单元 + 终态停止
（`--collect` 回收后只能登录服务器重建）”的模型已被“单进程 + 暂停/删除”取代。
WebUI 新建录制时可选择画质（原画/1080p/720p/480p），画质由 WebUI 直接传给录制引擎
（命令行入口经各平台 `record.sh` 等价透传），用于限制检测到的流清晰度；选择“原画”则
不设上限。文件列表支持点击“播放”在内嵌播放器中
预览任一录制片段（`/api/file` 支持 HTTP Range 拖动进度）。
WebUI 前端为 Vue 3 + Vite（源码在 `webui/frontend/src`），`webui/index.html` 是单文件构建产物。
改动前端后需重新构建：`cd webui/frontend && npm run build`（构建脚本会把 `dist/index.html` 复制回 `../index.html`）。

服务器状态监控页面位于 `https://20070809.xyz/sysmon/`。
