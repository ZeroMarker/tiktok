# Bilibili 推流与投稿

两条独立的对外路径，登录态都来自 `live.py login` 扫码（可存成多个账号分别使用）：

- **推流**（`live.py` / `push.sh` / `replay.sh` / `watch.sh` / `soop.sh`）——把直播源或本地
  `.mp4` 转推到 B 站**直播间**。WebUI（推荐，systemd 双模式互斥管理）或命令行两条用法。
- **投稿**（`upload.py`）——把本地 `.mp4` 投成 B 站**普通稿件**（分区投稿，不进直播间）。

| 文件 | 用途 |
|------|------|
| `live.py` | 开播/停播/改标题/查状态 + 扫码登录（`accounts`/`use` 管多账号）。移植自 [obs-bilibili-stream](https://github.com/Zarosmm/obs-bilibili-stream)，标准库 + 同目录 vendored Nayuki 二维码库，无新增依赖；来源与许可证见文件头部（上游 GPL-2.0 衍生） |
| `accounts.py` | 多账号登录态档案：存哪、选谁、被 `live.py`/`upload.py`/`webui/app.py` 共用 |
| `push.sh` | 直播推流：TikTok 直播源 → Bilibili。未开播时每 60 秒轮询，开播自动转推 |
| `replay.sh` | 文件轮播：本地 `.mp4` 按序循环 → Bilibili（默认 `-c copy`，`--encode` 重编码） |
| `watch.sh` | 轮播值守：先播本地文件，每 60 秒探测 TikTok，一开播就停轮播切转推 |
| `soop.sh` | 直播推流：SOOP 直播间 → Bilibili |
| `upload.py` | 稿件投稿：本地 `.mp4` 投成 B 站普通稿件（`push` 只传文件，`post` 提交稿件） |
| `webui/app.py` | 推流管理页后端（标准库 only），见下 |
| `systemd/` | `bili-live` / `bili-replay` / `bili-webui` 三个 user unit + `install.sh` |

## 登录态来源

登录态**只有一条获取途径：`live.py login` 扫码**——没有手工贴 Cookie 的入口。
扫码后可存成多个账号档案，推流和投稿各用一个，互不干扰。

```bash
python3 live.py login --account live      # 扫码登录到 live 账号（推流用）
python3 live.py login --account upload    # 扫码登录到 upload 账号（投稿用）
python3 live.py accounts                  # 列出所有账号 + 登录态有效期
```

档案落在 `~/.config/bili/accounts/<账号名>.json`（目录 700、文件 600，与
`push.env` / `live.env` 同居）。每个档案的字段：

| 字段 | 含义 |
|---|---|
| `cookies` | 扫码拿到的 `SESSDATA` / `bili_jct` / `DedeUserID` / `DedeUserID__ckMd5` / `sid` |
| `csrf_token` | 等于 Cookie 里的 `bili_jct`，投稿与开播的写接口都要用 |
| `mid` | 由 `nav` 推导 |
| `room_id` | 由 `room_id_by_uid` 推导，**仅开播需要**——投稿账号没有直播间时为空 |
| `rtmp_addr` / `rtmp_code` | 推流地址与推流码，每次 `start` 开播时刷新 |
| `area_id` / `title` | 上次开播的分区与标题，供管理页「关播状态下自动开播」复用 |

**没有直播间的账号也能登录。** 新注册账号调用 `room_id_by_uid` 会回
`code: 404` + `data: []`（该接口的 `message` 字段成功失败时都是 `ok`，不能
用来判别）。此时 `room_id` 留空，登录照常成功——**投稿完全不需要房间号**，
开播时才由 `_require_authed()` 补齐，补不到会明确提示「该账号仅可投稿，
开播需先在 B 站开通直播间」。`status` 会显示「无直播间（仅可投稿）」。

### 选择用哪个账号

每个工具各有一个默认账号，记录在 `~/.config/bili/accounts/defaults.json`：

| 工具 | 内置默认 | 用途 |
|---|---|---|
| `live.py` | `live` | 开播 / 推流 / 管理页 |
| `upload.py` | `upload` | 稿件投稿 |

```bash
python3 live.py use upload       # 以后 live.py（开播/推流）默认用 upload 账号
python3 upload.py use live       # 以后投稿默认用 live 账号
python3 live.py --account live status   # 临时指定，不改默认
python3 live.py --session /path/x.json status   # 显式路径，优先级最高
```

优先级：`--session` 路径 > `--account` 账号 > 该工具的默认账号。
管理页（`bili/webui/app.py`）跟随 `live.py` 的默认账号——改默认后重启
`bili-webui.service` 生效。

`accounts` 子命令会显示每个账号的 mid、房间号、SESSDATA 到期日和是否已过期：

```text
账号           mid          room_id    SESSDATA 到期          备注
------------------------------------------------------------
live         12345678     1234567    2027-03-09           默认用于 live；上次开播「示例房间」；有推流码
upload       87654321     7654321    2027-06-01           默认用于 upload
```

**SESSDATA 自带过期时间戳**（值形如 `值,过期时间,md5`），过期后所有接口回
`-101`；重新 `login` 即可。重新登录会覆盖该档案的 `cookies`/`csrf_token`/
`mid`/`room_id`，保留 `rtmp_addr`/`rtmp_code`/`area_id`/`title`。

### 迁移说明

改造前是单账号单文件 `bili/.bilibili_session.json`。首次运行任意 `live.py`
子命令时会**自动迁移**到 `accounts/live.json`，原文件改名保留为
`.bilibili_session.json.bak`；已存在目标档案时不覆盖、不重复迁移。

> **别和根目录的 `cookies.txt` 搞混**：那是 Netscape 格式、给 yt-dlp 抓
> TikTok/SOOP 流用的（`watch.sh` 自动携带），B 站侧一律走账号档案，不读它。

## 快速开始（推流，命令行）

```bash
python3 live.py login        # 终端显示二维码，Bilibili App 扫码（投稿也用它登录）
python3 live.py areas        # 列出直播分区，记下子分区 ID
python3 live.py start --area 646 --title "频道名" --print-export
bash replay.sh "../recordings/tiktok/<频道目录>"    # 或 bash push.sh <tiktok_username>
python3 live.py update --title "新标题"
python3 live.py stop         # 关播（先停推流进程再关）
```

## WebUI（推荐）

已并入 Live Stream Toolkit 仓库（本目录 `bili/`，独立仓库 ZeroMarker/bili 为历史来源）：与录制侧同仓，`watch.sh` 自动携带仓库根 `cookies.txt`。两种推流模式**互斥**（同时最多跑一个，启动一个会自动停掉并 disable 另一个）：

- 直播推流 `bili-live.service`（`push.sh`）
- 文件轮播 `bili-replay.service`（`replay.sh`）

```bash
bash systemd/install.sh   # 装 3 个 user unit，bili-webui 直接 enable --now
```

- 本地：`http://127.0.0.1:8767`（仅回环，无应用层认证）
- 公网：`https://bili.20070809.xyz`（Caddy 反代 + basicauth，与站群同凭证）

管理页可做：启停两种模式、看 unit 状态与 ffmpeg 是否在推、看 journal 日志、开播/停播/改标题。开播后自动把新推流码保存到 `~/.config/bili/push.env`（权限 600）。手动等价操作：`systemctl --user enable --now bili-live.service`（先停另一个）。

API（JSON）：`GET /api/health|status|logs?which=live|replay|webui&tail=`，
`POST /api/mode {mode,target|paths,encode}`、`POST /api/stop`、
`POST /api/room {action:start|stop|update, area?, title?}`。

## 推流密钥来源

转推脚本拼接 `BILIBILI_PUSH_URL` + `BILIBILI_PUSH_CODE`。来源按优先级：WebUI 的 `~/.config/bili/push.env` → 进程环境及
`~/.bashrc` 的 `source` → 兜底直读 `~/.bashrc` 中的导出项（`push.sh`/`replay.sh`/
`watch.sh` 均有该兜底，systemd 下靠它工作）。每次 `live.py start` 推流码都会换：
命令行开播后需用会话文件中的新码更新配置：已有 `~/.config/bili/push.env` 时更新该文件，否则更新 `~/.bashrc`。`--print-export` 不回显完整推流码。WebUI 开播自动同步到独立配置，无需预先编辑 `.bashrc`。

WebUI 支持表单草稿记忆、后台刷新和持续操作反馈。控制请求互斥，另一项操作未完成时返回 409；多页面操作不会同时启动两路推流。升级后运行 `bash systemd/install.sh` 更新 unit，并执行 `systemctl --user restart bili-webui.service` 加载新后端。

```bash
export BILIBILI_PUSH_URL="rtmp://txy3.live-push.bilivideo.com/live-bvc/"
export BILIBILI_PUSH_CODE="your-stream-key"
```

## 各脚本说明

```bash
bash push.sh <tiktok_username>              # TikTok 直播（需登录态主播用 watch.sh，其自动携带 cookies.txt）
bash soop.sh <SOOP直播间URL>                # SOOP 直播
bash replay.sh <文件|目录> [更多...] [--encode] [--dry-run]
bash watch.sh <tiktok_username> [replay.sh 参数...]   # 轮播值守
```
- `replay.sh`：目录按文件名排序展开其中 `*.mp4`，多输入按序连播、播完循环；
  默认 `-c copy`（h264+aac 源几乎不占 CPU）；跨分段分辨率/帧率跳变卡顿时用
  `--encode`（x264 veryfast + aac，640x1280 约占半核）；`--dry-run` 只打印
  ffmpeg 命令（推流码打码）。日志 `./logs/ffmpeg_replay_*.log`，断线 5 秒重推。
- `push.sh`/`soop.sh`：断线 10 秒重抓；日志 `./logs/ffmpeg_{tiktok,soop}_*.log`。

## 稿件投稿（upload.py）

把录制文件投成 B 站**普通稿件**（分区投稿，与直播转推是两条路）。复用 `live.py login`
的登录态。`--session` / `--state` / `--account` 写在子命令前后都可以：

```bash
python3 upload.py status                                     # 检查登录态（默认 upload 账号）
python3 upload.py --state s.json push <文件|目录>            # 只传文件，不建稿件
python3 upload.py --state s.json post --title "标题" --tid 21 \
    --tag "a,b" --desc "简介" --source "来源" --part-title-prefix "标题"
python3 upload.py post <文件|目录> --title "标题" --tid 21   # 一条龙（上传 + 提交）
python3 upload.py post ... --account live                   # 临时改用别的账号投稿
```

登录态默认用 `upload` 账号（与推流的 `live` 账号分开），见上文「登录态来源」。
首次使用先 `python3 live.py login --account upload` 扫码。

- `push` / `post` 共用一份 state JSON（默认 `upload-state.json`，已 gitignore），
  记录每个文件的 `filename`（**无后缀**）与 `cid`；中断后重跑会跳过已传好的文件，
  只重传失败/新增的。
- **录播一律合成 1 稿多分 P**（`--part-title-prefix` 生成 `<前缀> 01`、`02`…）：
  一次提交只审一次。拆成几十个独立稿件会撞 B 站连续提交限流（约 10 稿触发
  `code: 601`「上传视频过快」，网页端可能转为要短信验证）。
- `--copyright` 默认 `2` 转载并要求 `--source`：B 站投稿接口明确「录制他人直播
  （包括授权录制）不属于自制内容，请选转载」。标转载来源比标自制更安全。
- `--only-self` 先设仅自己可见，在创作中心确认封面/标题/分 P 顺序后再转公开。
- 分区 `--tid`：用 `POST /x/vupre/web/archive/types/predict`（`csrf` + `filename` +
  `title`）拿 5 个候选子分区，录播通常落在 21 生活/日常。旧文档写的
  `/x/web/archive/pre` 已 404。标签可先用 `GET /x/vupre/web/topic/tag/check` 验可用性。
- 提交成功只代表**进审核**：立刻 `x/web-interface/view` 查会返回 `-404`，
  纯 ASCII 标题约 1 分钟过审。
- **只投普通稿件**。竖屏（story）投稿没有公开接口文档，biliup-rs 也不支持；
  竖屏片源（432x864）走普通稿件时播放器两侧有黑边，内容与清晰度不受影响。
- 接口细节（含各接口的实测响应结构）见
  [bili/docs/bilibili-upload-api.md](docs/bilibili-upload-api.md)。

## 录制文件质检

轮播黑屏/卡住多半是片源问题（录制时源卡顿留下空洞或坏帧），播前抽查：

```bash
# 空洞扫描：输出 gap 即冻结时长（>5s 即会冻结）
ffprobe -v error -select_streams v -show_entries packet=pts_time -of csv <file> \
  | awk -F, 'NR>1 && $2-p>5 {print "gap " $2-p "s at " p "s"} {p=$2}'
# 解码扫描：大量 concealing 即黑屏/花屏段
ffmpeg -hide_banner -v error -i <file> -f null - 2>&1 | grep -c "concealing"
```

坏段用 `ffmpeg -ss <秒> -i <file> -c copy <fixed>.mp4` 切掉；多规格混杂用 `--encode`。

## 已知限制

### 推流（2026-09-06 实测）

- 标题禁 emoji（接口拒收“房间名不能有表情符号”），用纯文本。
- `update` 成功只代表提交进审核：`audit_info.audit_title_reason` 为“进入审核”时
  公示标题保持默认直到过审；含真实艺人名的标题会被判疑似冒充而长期卡审或驳回，
  纯 ASCII 标题约 1 分钟过审。
- 开播表单不带 `build` 参数：全参数签名必回 `-3 签名错误`，去掉后通过；
  偏离已在 `live.py` 注释与 `tests/test_bili_live.py` 回归测试中锁定。
- 开播可能触发人脸验证（接口码 60024/60043），按终端提示扫码完成后再重试。

### 投稿（2026-09-28 实测，13 分 P 录播 BV11Ca36sE35）

- 只能投**普通稿件**；竖屏（story）投稿无公开接口文档，biliup-rs 亦不支持。
  432x864 竖屏片源投普通稿件后，播放器两侧有黑边，内容与清晰度不受影响。
- 连续提交约 10 个稿件触发 `code: 601`「上传视频过快」，此时网页端手动上传
  可能要求短信验证。录播要合成 1 稿多分 P。
- 提交后立刻查 `x/web-interface/view` 返回 `-404` 属正常——稿件还在审核，
  过审后才可见。
- 录播必须标转载（`copyright=2` + `source`）：B 站投稿接口明确「录制他人直播
  （包括授权录制）不属于自制内容，请选转载」。
- B 站不校验分片 ETag 内容，但 `upload.py` 仍读真实 ETag，读不到回退填 `etag`。

## 故障排查

- TikTok 判未开播但用户侧在播：机房 IP 可能被 SlardarWAF/GroupBlock 封锁
  （见本仓库 `docs/archive/tiktok-error.md`），以用户侧为准，或从浏览器 Network 面板抓
  `m3u8`/FLV 直链；亦可用 `cookies.txt` 登录态（部分主播需登录才返流）。
- unit 起不来、`203/EXEC`：脚本缺可执行位（`chmod +x`），`systemd-analyze verify` 校验。
- 双推流冲突：同一房间同时只能一路流；`status` 报 `conflict` 时停掉一路。
  旧 hub 托管进程与 systemd 不互通，迁移时先停旧进程（`hub stop <name>`）。
- 看日志：管理页日志区，或 `journalctl --user -u bili-live.service`。
- 投稿报 `-101`/`-111`：`live.py login` 会话过期或 csrf 不匹配，重新登录。
- 投稿报 `601`：连续提交过多，等十几分钟；确认没有在拆成大量独立稿件。
- 「账号 upload 尚未登录」：投稿走的是独立的 `upload` 账号，需要单独扫码
  `python3 live.py login --account upload`；`live.py accounts` 看现状。
- 投稿传文件时 `Name or service not known`：upos 节点 DNS 抖动，重跑即可
  （state 里已完成的文件会跳过，不重复传）。

## 待办

- [ ] ai_haneda_0922 抓流：机房 IP 被 TikTok SlardarWAF/GroupBlock 封锁，
  2026-09-07 用正式引擎链（yt-dlp / impersonate / curl_cffi 兜底）复测仍无流
  （账号存在，昵称 羽田 あい）。条件：拿到日本 VPS 或用户侧 `m3u8` 直链。

## 许可证

除另有声明外，本项目使用根目录 `LICENSE` 中的 MIT License。
`live.py` 是 GPL-2.0 上游代码的衍生移植，按 `COPYING.GPL-2.0` 分发；
`qrcodegen.py` 保留其文件头中的 MIT 许可与作者声明。
