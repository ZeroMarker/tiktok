# tubasa__mai 直播录制失败原因分析

## 现象

- 其他 TikTok 主播（emiri.okazaki、mizuno_asahi 等）均可正常录制
- tubasa__mai 目录为空，从未成功录制过
- yt-dlp 返回：`The channel is not currently live`
- 页面实际返回：`"roomId":""`、`"LiveRoomInfo":null`
- 用户在美国网络环境下操作，非地域封锁问题

---

## 可能原因（按可能性排序）

### 1. TikTok 对特定账号返回不同页面结构

TikTok 对不同主播返回的直播数据格式可能不同。部分主播的 `roomId` 嵌入在页面深层 JSON 中（如 `loaderData["(uniqueId).live/layout"].dehydratedState.queries[0].state.data.data.user`），而非标准位置，导致 yt-dlp 提取失败。

参考：[yt-dlp#10407](https://github.com/yt-dlp/yt-dlp/issues/10407)

### 2. 验证码/反爬挑战 (Captcha)

TikTok 对某些主播或某些时间段返回验证码挑战页面，yt-dlp 无法识别，误判为"未开播"。

- 现象：HTTP 200 但页面中没有 `roomId`
- 判断依据：`botType":"others"` 表明 TikTok 识别到非浏览器请求
- 参考：[yt-dlp#9418](https://github.com/yt-dlp/yt-dlp/issues/9418)、[yt-dlp#11921](https://github.com/yt-dlp/yt-dlp/issues/11921)

### 3. 需要登录态 (Cookie)

部分主播的直播信息必须登录后才返回。`login=0` 表明请求未登录。

- 主播可能设置了年龄限制或特定观众限制
- 部分国家/地区（如意大利）强制要求登录才能看直播
- 解决：传入浏览器 Cookie（`--cookies-from-browser chrome`）

### 4. 直播源类型不同 (FLV vs HLS)

部分主播的直播源使用 FLV 格式而非 HLS，yt-dlp 获取 m3u8 URL 时失败。

- 现象：API 返回 `"liveUrl":""` 但实际有 FLV 流地址
- 参考：[yt-dlp#6459](https://github.com/yt-dlp/yt-dlp/issues/6459)

### 5. TikTok API 响应结构变化

TikTok 频繁调整直播 API 的 JSON 结构，yt-dlp 的解析路径可能不匹配该主播的数据结构。

- 旧结构：`LiveRoomInfo.liveUrl`
- 新结构：`LiveRoom.liveRoomUserInfo.user.roomId`
- 参考：[yt-dlp#10407](https://github.com/yt-dlp/yt-dlp/issues/10407)

### 6. IP/设备指纹被限制

即使在美国网络下，TikTok 仍可能对特定 IP 段或请求指纹（User-Agent、TLS 指纹等）做限流，导致关键数据不返回。

---

## 解决方案

### 方案 A：传入浏览器 Cookie（推荐首选）

```bash
# 从浏览器导出 Cookie 后录制
yt-dlp --cookies-from-browser chrome "https://www.tiktok.com/@tubasa__mai/live"
```

### 方案 B：启用 Impersonate（模拟浏览器指纹）

```bash
yt-dlp --impersonate chrome "https://www.tiktok.com/@tubasa__mai/live"
```

### 方案 C：伪造地理定位

```bash
yt-dlp --xff US "https://www.tiktok.com/@tubasa__mai/live"
```

### 方案 D：降级使用移动端 API

```bash
# 使用移动端分享链接格式
yt-dlp "https://m.tiktok.com/v/@tubasa__mai/live"
```

### 方案 E：使用第三方云录制服务

如果 yt-dlp 始终无法解决，可尝试 TikRec 或 GREC 等云端录制服务。

---

## 参考链接

- [yt-dlp#9418 - Captcha challenge 导致误判](https://github.com/yt-dlp/yt-dlp/issues/9418)
- [yt-dlp#11921 - JSON metadata 请求后误判](https://github.com/yt-dlp/yt-dlp/issues/11921)
- [yt-dlp#10407 - JSON 结构变化导致解析失败](https://github.com/yt-dlp/yt-dlp/issues/10407)
- [yt-dlp#6459 - 部分直播流无法获取 m3u8 URL](https://github.com/yt-dlp/yt-dlp/issues/6459)
- [yt-dlp#16850 - HTTP 400 错误 + 录制修复 PR](https://github.com/yt-dlp/yt-dlp/issues/16850)
- [yt-dlp PR #16783 - TikTok live extractor 修复](https://github.com/yt-dlp/yt-dlp/pull/16783)

---

## 验证步骤

下次该主播直播时：

1. 浏览器打开 `https://www.tiktok.com/@tubasa__mai/live` 确认直播画面正常
2. 运行以下命令逐项排查：

```bash
# 无参数（当前行为）
yt-dlp "https://www.tiktok.com/@tubasa__mai/live"

# 带 Cookie
yt-dlp --cookies-from-browser chrome "https://www.tiktok.com/@tubasa__mai/live"

# Impersonate
yt-dlp --impersonate chrome "https://www.tiktok.com/@tubasa__mai/live"

# Verbose 查看详细错误
yt-dlp -v "https://www.tiktok.com/@tubasa__mai/live"
```

3. 哪个命令成功拿到直播地址，就把对应参数加到 `record.sh` 中

---

# emma_kusunoki 直播检测失败 (2026-07-26)

## 现象

- yt-dlp 能从 SIGI_STATE 解析到 roomId，但该 roomId 是用户永久 roomId
- webcast API 返回 status_code=0 / status=4 (4003110: 用户未开播)
- TikTok 页面标题显示 "is LIVE" 但实际 liveRoom.status != 2
- 用户确认主播正在直播，但所有 API 检测均返回未开播

## 分析

TikTok 的直播 API 对不同主播返回的数据一致性不同。
部分主播可能处于某种"中间状态"（例如测试推送、有限区域直播），
导致浏览器能看到直播画面但 API 不返回正式 roomId。

## 解决方案

### 使用 fallback_tk.sh（新增）

当 yt-dlp 持续失败时，改用备用脚本：

```bash
bash ~/tiktok/tk/fallback_tk.sh emma_kusunoki
```

该脚本按优先级依次尝试 4 种检测方法：
1. yt-dlp 默认（带 --impersonate）
2. yt-dlp + --xff US（伪造地理位置）
3. yt-dlp + mobile 域名
4. Python live_check.py（curl_cffi 直接解析 SIGI_STATE，再次确认）

### Python live_check.py

详细的 Python 检测脚本在 `~/tiktok/tk/live_check.py`，可单独使用：

```bash
python3 ~/tiktok/tk/live_check.py emma_kusunoki
```

支持：
- 解析 SIGI_STATE 中的 liveRoom
- 解析 __UNIVERSAL_DATA_FOR_REHYDRATION__
- 调用 webcast API
- 全文搜索 roomId 并逐一尝试

## 遗留问题

如果所有 API 检测方法都失败（SIGI_STATE 中 liveRoom.status!=2、
CurrentRoom 为空、webcast API 返回 4003110），
则可能是 TikTok 内部状态不允许外部 API 检测到直播。
这只能说明 Web API 检测失败，不能说明 yt-dlp 无法录制。应先运行
`bash tk/record.sh <username>` 让 yt-dlp 持续轮询；若 yt-dlp 也持续失败，
再检查 Cookie、实际出口地区或从可播放的浏览器获取流 URL。

---

# emma_kusunoki 直播检测失败 (2026-07-27) — GroupBlock 确认

## 现象

- 用户确认主播正在直播
- SIGI_STATE 中 `liveRoom.status=2` 但 `roomId=None`、`roomInfo=null`
- 页面 `CurrentRoom.loadingState.enterRoom=0`（未进入房间）
- yt-dlp / curl_cffi / Playwright 三种方案均未发现流地址
- Playwright 真实浏览器渲染后看到 `webcast/room/enter` 返回 **403**

## 根因

**room/enter API 返回 200 但 status_code=4003157**

```json
{
  "status_code": 4003157,
  "punish_info": {
    "punish_type": "lcc",
    "punish_perception_code": "TNS_Host_GroupBlock_LCC_DSA_V1"
  }
}
```

- `TNS_Host_GroupBlock_LCC_DSA_V1`：主播所在区域/网络已被 TikTok 分组封锁
- `LCC` = Live Content Control（直播内容控制）
- `GroupBlock` = 对特定 IP 段/地区/网络分组的直播流屏蔽
- 与昨天猜测不同 —— 不是数据一致性问题，而是 TikTok **主动封锁**了该主播的流对本 IP 段的访问

## 与其他主播对比

| 主播 | 状态 | roomId | room/enter 响应 |
|------|------|--------|----------------|
| murakami_yuka | ✅ 正常录制 | 有 | 正常返回流地址 |
| moena_skofficial | ✅ 正常录制 | 有 | 正常返回流地址 |
| emma_kusunoki | ❌ 封锁 | None/null | 4003157 GroupBlock |

## 解决方案

### 方案 1：使用日本/其他区域 VPS 中转

TikTok 的 GroupBlock 基于 IP 归属地/ASN。更换不同区域的服务器可能绕过限制。

### 方案 2：用户提供流 URL

如果用户的客户端能正常观看，可以从浏览器开发者工具 → Network → 过滤 `flv` 或 `m3u8`，复制流 URL 直接给 ffmpeg 录制。

## 后续改进

- standby_tk.sh 脚本新增对 `4003157` / `GroupBlock` 的快速识别，不浪费重试次数
- 若检测到 GroupBlock，立即输出明确提示而非继续循环

---

# emma_kusunoki 补充分析 (2026-07-28) — tk 脚本实际成功

## 事实还原

2026-07-28 凌晨的实际情况与当初分析有偏差：

| 时间 (CST) | 事件 |
|------------|------|
| 00:30 | tmux 轮询中的 `tk` 脚本通过 **yt-dlp** 成功拿到 FLV 流 URL，开始录制 |
| 00:42 | 用户通知主播在线，我使用 Playwright/webcast API 检测，**撞上 GroupBlock** |
| 00:50 | 错误结论「全部方法均被封锁」，写入 error.md |
| 00:30–02:03 | **录制一直在进行**，共 10 个片段 ~750MB |

## 根因澄清

**GroupBlock (4003157) 只封锁了 web API 路径 `webcast/room/enter`，但 yt-dlp 获取 FLV 直链的路径不受影响。**

- `tk` 脚本第 85 行使用 `yt-dlp ... --get-url` 直接获取 FLV 流地址
- yt-dlp 有独立的 TLS 指纹模拟和 cookie 管理，不走 webcast API
- `live_check.py`/Playwright 测试使用的是 web API，被 GroupBlock 拦截
- **tk 脚本的轮询机制自动绕过了这个限制**

## 教训

1. **不要仅用 web API 检测结果判断能否录制** — web API 可能被 GroupBlock 拦，但 yt-dlp 仍能拿到流
2. 测试 live 可用性时，应直接跑 `yt-dlp --get-url` 而不是 Playwright/web API
3. `tk` 脚本的轮询模式本身就是最好的检测工具——它在后台一直试，能录自然会录上

## 验证命令

```bash
# 直接验证 yt-dlp 能否拿到流（即使 web API 返回 GroupBlock）
yt-dlp "https://www.tiktok.com/@emma_kusunoki/live" -f "b[ext=flv]" --get-url
```

---

# act.jp_official 直播地址获取失败（2026-07-29）

## 结论

`act.jp_official` 当前确实正在直播，但 TikTok 的不同 LIVE API 返回结果不一致：

- 新接口确认用户正在直播，并返回直播间 ID
- 新接口没有返回 `streamData`，因此无法提取 FLV/HLS 播放地址
- `yt-dlp` 使用的旧接口返回错误，导致其误报 `The channel is not currently live`

这不是用户名错误，也不是单纯的 `yt-dlp` 版本过旧问题。

## 复现环境

```text
yt-dlp: 2026.07.04
Python: 3.12.3
curl_cffi: 0.15.0
ffmpeg: 6.1.1
直播 URL: https://www.tiktok.com/@act.jp_official/live
直播间 ID: 7667857762663156500
```

执行：

```bash
yt-dlp -v "https://www.tiktok.com/@act.jp_official/live"
```

结果：

```text
[tiktok:live] 7667857762663156500: Downloading JSON metadata
ERROR: [tiktok:live] act.jp_official: The channel is not currently live
```

## API 检查结果

### 新接口

请求：

```text
https://www.tiktok.com/api-live/user/room?aid=1988&sourceType=54&uniqueId=act.jp_official
```

关键返回值：

```json
{
  "statusCode": 0,
  "user_status": 2,
  "roomId": "7667857762663156500",
  "streamData": null
}
```

其中 `user_status=2` 明确表示正在直播，但 `streamData=null`，所以仍然没有可交给 `ffmpeg` 的播放地址。

### 旧接口

请求：

```text
https://webcast.tiktok.com/webcast/room/info/?aid=1988&room_id=7667857762663156500
```

关键返回值：

```json
{
  "status_code": 4003110,
  "data": {
    "prompts": "..."
  }
}
```

当前 `yt-dlp` 的 TikTok LIVE 提取器首先依赖该旧接口。接口没有返回正常直播数据后，提取器将其解释为未开播。

## 已测试但无效

模拟 Chrome 请求：

```bash
yt-dlp --impersonate chrome \
  "https://www.tiktok.com/@act.jp_official/live"
```

增加日本 `X-Forwarded-For`：

```bash
yt-dlp --xff JP --impersonate chrome \
  "https://www.tiktok.com/@act.jp_official/live"
```

两种方式仍然返回 `The channel is not currently live`。`--xff JP` 仅修改请求头，不能代替真正的日本出口 IP。

## 原因判断

该问题符合 yt-dlp 已登记的 TikTok LIVE 提取器故障：

- TikTok 的旧直播接口不稳定，会对实际正在直播的账号返回错误
- 新接口能正确判断直播状态，但部分直播不返回流数据
- 直播可能额外受到登录状态、地区、年龄或 TikTok 内容访问策略限制

相关修复 PR 已改用 `api-live/user/room` 接口，并放宽不同接口状态不一致时的判断，但截至本次排查时仍未合并。

## 建议处理顺序

### 1. 使用已登录浏览器 Cookie

先在同一台机器、同一公网 IP 的浏览器中登录 TikTok，并确认浏览器可以播放该直播：

```bash
yt-dlp \
  --cookies-from-browser chrome \
  --impersonate chrome \
  "https://www.tiktok.com/@act.jp_official/live"
```

Firefox：

```bash
yt-dlp \
  --cookies-from-browser firefox \
  --impersonate chrome \
  "https://www.tiktok.com/@act.jp_official/live"
```

使用导出的 Netscape 格式 Cookie：

```bash
yt-dlp \
  --cookies cookies.txt \
  --impersonate chrome \
  "https://www.tiktok.com/@act.jp_official/live"
```

### 2. 使用真实日本出口 IP

如果带 Cookie 仍没有 `streamData`，通过日本代理运行：

```bash
yt-dlp \
  --proxy "http://127.0.0.1:7890" \
  --cookies cookies.txt \
  --impersonate chrome \
  "https://www.tiktok.com/@act.jp_official/live"
```

Cookie 登录时使用的地区/IP 与 `yt-dlp` 请求地区最好保持一致。

### 3. 等待上游修复

关注：

- [yt-dlp Issue #11921](https://github.com/yt-dlp/yt-dlp/issues/11921)
- [yt-dlp PR #16783](https://github.com/yt-dlp/yt-dlp/pull/16783)

即使应用该 PR，只要 TikTok 仍返回 `streamData=null`，仍需有效登录 Cookie或可访问该直播的地区 IP 才可能取得播放地址。
