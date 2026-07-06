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
