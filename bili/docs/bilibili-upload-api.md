# Bilibili 视频投稿接口

面向**普通稿件**（分区投稿）的接口说明，供 `bili/upload.py` 的实现与维护参考。
接口均需登录态（Cookie），未登录返回 403 / -101。

> 标注「实测」的响应结构来自 2026-09-28 对 `BV11Ca36sE35`（13 分 P 录播）的
> 实际上传验证；标「旧资料」的地方是已失效的写法，保留仅为对照。
>
> **动手前先看 [`bili/README.md`](../README.md) 的「稿件投稿」一节**——
> `upload.py` 已覆盖本文档全部步骤，直接用它即可。

---

## 1. 流程总览

B 站投稿（Web 端）分为 **文件上传** 和 **稿件提交** 两个阶段：

```text
准备登录态 (Cookie SESSDATA + CSRF bili_jct)
        │
        ▼
[可选] 封面上传  POST /x/vu/web/cover/up ──────────────► cover url
        │
        ▼
1. 预上传      GET  /preupload ────────────────────────► auth + biz_id + upos_uri
        │                                                  （chunk_size 也在这里）
        ▼
2. 登记上传    POST {base}?uploads ────────────────────► upload_id
        │
        ▼
3. 分片上传    PUT  {base}?partNumber=...  (循环，每片一次)
        │
        ▼
4. 合并完成    POST {base}?output=json&name=…&uploadId=… ──► OK
        │
        ▼
5. 提交稿件    POST /x/vu/web/add/v3 ──────────────────► aid / bvid
        │
        ▼
[可选] 编辑     POST /x/vu/web/edit
```

其中 `{base}` 是 1、2、3、4 步共用的上传 URL：

```text
https://{预上传 endpoint 去 //}/{upos_uri 去 upos://}
```

**核心要点：**

- 文件走「分片直传」到 CDN 域名（`upos-cs-upcdn*.bilivideo.com`），不是 multipart 表单；
- 所有 upos 请求都要带 `X-Upos-Auth: {预上传的 auth}` 头；
- `biz_id` 是提交稿件时每个分 P 的 `cid`；
- `filename` 取 `upos_uri` 的无后缀文件名，**不是**合并接口的返回值（它不返回文件名）；
- 提交稿件用 `/x/vu/web/add/v3` + **JSON**；`/x/vu/client/add` 已失效。

---

## 2. 前置准备

### 2.1 登录态 Cookie

本仓库已实现扫码登录，**直接复用 `bili/live.py` 的账号档案**
（`~/.config/bili/accounts/<账号名>.json`，目录 700、文件 600）。投稿默认用
`upload` 账号、推流用 `live` 账号；完整来源链路见
[`bili/README.md` 的「登录态来源」](../README.md#登录态来源)，此处只列投稿用到的：

```bash
python3 live.py login --account upload   # 终端二维码，Bilibili App 扫码
python3 upload.py status                 # 顺带确认登录态与 SESSDATA 到期日
python3 live.py accounts                 # 列出所有账号
```

档案里的 `cookies` 字段已包含下列全部 Cookie：

| Cookie 名 | 用途 |
|---|---|
| `SESSDATA` | 登录凭证（核心，自带过期时间戳） |
| `bili_jct` | CSRF Token 来源 |
| `DedeUserID` | 用户 ID |

> 仓库根目录的 `cookies.txt` 是 Netscape 格式、给 yt-dlp 抓 TikTok/SOOP 流用的，
> B 站侧一律读账号档案，不读它。

### 2.2 CSRF Token

- 值就是 Cookie `bili_jct` 的值，账号档案里的 `csrf_token` 字段同值；
- 写接口（`add/v3` / `edit` / `cover/up` / `types/predict`）都要带 `csrf`。

### 2.3 统一请求头

所有请求建议携带：

```http
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36
Referer: https://member.bilibili.com/platform/upload/video/frame
Origin: https://member.bilibili.com
Cookie: SESSDATA=...; bili_jct=...; DedeUserID=...
```

---

## 3. 接口明细

### 3.1 预上传 `GET /preupload`

拿上传节点、鉴权串与 `upos` 路径。**响应是扁平对象，没有 `data` 包装层**，
也没有 `uptoken` / `bili_checksum` 字段（旧资料里的这些字段已不存在）。

```
GET https://member.bilibili.com/preupload
Cookie: SESSDATA=...; bili_jct=...
```

| Query 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `name` | string | 是 | 本地文件名，会影响返回的 `upos_uri` |
| `r` | string | 是 | 固定 `upos` |
| `profile` | string | 是 | 普通稿件固定 `ugcupos/bup`（`ugcfx/bup` 需另传 metadata/frame.zip） |
| `size` | int | 是 | 文件字节数 |
| `ssl` | int | 否 | 固定 `0` |
| `version` / `build` | string/int | 否 | 固定 `2.14.0` / `2140000` |
| `probe_version` | int | 否 | 固定 `20221109` |
| `upcdn` | string | 否 | 线路，默认 `txa`（另有 `ws`/`qn`/`bda2`/`alia`） |
| `zone` | string | 否 | 固定 `cs` |

**响应示例（2026-09-28 实测）：**

```json
{
  "OK": 1,
  "auth": "ak=1494471752&cdn=%2F%2Fupos-cs-upcdntxa.bilivideo.com&os=upos&sign=...&timestamp=...&uid=...&uip=...&uport=...&use_dqp=0",
  "biz_id": 42272754632,
  "chunk_retry": 10,
  "chunk_retry_delay": 3,
  "chunk_size": 10485760,
  "endpoint": "//upos-cs-upcdntxa.bilivideo.com",
  "endpoints": ["//upos-cs-upcdntxa.bilivideo.com", "//upos-cs-upcdnalia.bilivideo.com"],
  "expose_params": null,
  "put_query": "os=upos&profile=ugcupos%2Fbup",
  "threads": 5,
  "timeout": 1200,
  "uip": "149.118.53.219",
  "upos_uri": "upos://ugcever/n260928ad1t7th5na4etco2mdu8y4r2n.mp4"
}
```

**字段说明：**

| 字段 | 说明 |
|---|---|
| `auth` | 鉴权串，后续所有 upos 请求都要放进 `X-Upos-Auth` 头 |
| `biz_id` | **业务 ID，提交稿件时就是分 P 的 `cid`**，必须留档 |
| `chunk_size` | 服务端指定的分片大小，**用它而不是自己拍的 4MB** |
| `chunk_retry` | 服务端建议的分片重试次数 |
| `endpoint` | 上传节点，**自带 `//` 前缀**（协议相对），见下方拼接口径 |
| `upos_uri` | 形如 `upos://{bucket}/{文件名}` |

**URL 拼接口径（易错）**：`endpoint` 自带 `//`，`upos_uri` 自带 `upos://`，
直接字符串相加会漏掉中间的 `/`：

```python
host = endpoint.strip().removeprefix("//").rstrip("/")
path = upos_uri.split("://", 1)[-1].lstrip("/")
base = f"https://{host}/{path}"   # https://upos-cs-upcdntxa.bilivideo.com/ugcever/xxx.mp4
```

---

### 3.2 登记上传 `POST {base}?uploads`

**这一步不能省**：预上传只给授权，真正要传字节前要先向同一个 URL 登记一次，
拿到本次上传的 `upload_id`（与 `biz_id` 是两回事，`biz_id` 才是稿件的 `cid`）。

```
POST https://{endpoint}/{bucket}/{filename}?uploads=&output=json&profile=ugcupos/bup&filesize=…&partsize=…&biz_id=…
X-Upos-Auth: {预上传的 auth}
```

`uploads=` 必须带等号且值为空（漏掉会 404）。`filesize`/`partsize`/`biz_id`
取预上传的 `size`/`chunk_size`/`biz_id`。

**响应：**

```json
{ "OK": 1, "bucket": "ugcever", "key": "/n2609xxx.mp4", "upload_id": "8c3c1d61-a249-4b0c-bae1-b6e09b14c281" }
```

---

### 3.3 分片上传 `PUT {base}`

文件按 `chunk_size` 切片，逐片直传。**URL 与登记时完全相同**，
分片信息全在 query 上。

| Query 参数 | 类型 | 说明 |
|---|---|---|
| `partNumber` | int | 分片序号，从 `1` 开始 |
| `chunk` | int | 分片序号，**从 `0` 开始**（与 `partNumber` 差 1，不是字节数） |
| `chunks` | int | 总分片数 |
| `size` | int | **本分片**字节数（不是文件总大小） |
| `start` | int | 本分片起始字节偏移 |
| `end` | int | 本分片结束字节偏移（`start + size`） |
| `total` | int | 文件总字节数 |
| `uploadId` | string | 登记返回的 `upload_id` |

**请求示例（curl）：**

```bash
curl -X PUT "${base}?partNumber=1&uploadId=${upload_id}&chunk=0&chunks=4&size=4194304&start=0&end=4194304&total=16777216" \
  -H "X-Upos-Auth: ${auth}" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @part_01.bin
```

**响应：**

- 成功：`HTTP 200`，body 为 `MULTIPART_PUT_SUCCESS`；
- 响应头 `ETag` 带引号（如 `"abc123"`），合并时要去掉引号；
- 服务端不校验 etag 内容，biliup 直接填固定字符串 `etag` 也能过，
  但读真实 ETag 更稳妥；读不到时回退填 `etag`（`upload.py` 的做法）。

**分片建议：**

- 用预上传返回的 `chunk_size`（实测 10MB），不要自己拍 4MB；
- 总分片数不宜过多（单文件按 10MB 算，2GB 约 200 片）；
- 支持断点续传：已上传分片可跳过（幂等 PUT）。

---

### 3.4 合并完成 `POST {base}`

所有分片上传完毕后，通知服务器合并文件，拿到 `filename`。

```
POST {base}?output=json&name={原始文件名}&profile=ugcupos/bup&uploadId={upload_id}&biz_id={biz_id}
X-Upos-Auth: {auth}
Content-Type: application/json
```

注意 `name`/`profile`/`uploadId`/`biz_id` 都在 **query** 上，正文只有 `parts`：

```json
{ "parts": [ { "partNumber": 1, "eTag": "abc123" } ] }
```

`parts` 必须**按分片序号连续有序**（1,2,3…），不能乱序、不能跳号。

**响应示例（2026-09-28 实测）：**

```json
{ "OK": 1, "location": "ugcever/n260928ad1bz7vpwbo05fk28guzw96ul.mp4", "bucket": "ugcever", "key": "/n260928ad1bz7vpwbo05fk28guzw96ul.mp4" }
```

**响应里没有 `filename` 字段**。提交稿件要用的 `filename` 直接取预上传
`upos_uri` 的**无后缀文件名**（`Path(upos_uri).stem`），与 `location`/`key` 的末段一致。
实测 `upos_uri=upos://ugcever/n260928ad1bz7.mp4` → 提交时 `filename=n260928ad1bz7`。

---

### 3.5 提交稿件 `POST /x/vu/web/add/v3`

文件上传完成后，提交稿件元信息，正式发布。

> 旧资料写的 `/x/vu/client/add`（表单编码）已失效，biliup 源码里也标了
> "客户端接口已失效"。现在用 Web 端接口，**正文是 JSON**，`csrf` 放在 URL
> query 上（正文里也要带一份）。

```
POST https://member.bilibili.com/x/vu/web/add/v3?t={unix毫秒}&csrf={bili_jct}
Content-Type: application/json
Cookie: SESSDATA=...; bili_jct=...
```

**正文参数：**

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | 是 | 稿件标题，最多 80 字符 |
| `tid` | int | 是 | 分区 ID（见第 4 节） |
| `copyright` | int | 是 | `1` 自制，`2` 转载 |
| `source` | string | 转载必填 | 转载来源，**只在 `copyright=2` 时传** |
| `videos` | array | 是 | 分 P 数组，见下 |
| `tag` | string | 是 | 标签，英文逗号分隔，最多 10 个 |
| `desc` | string | 否 | 简介，最多 2000 字符 |
| `desc_format_id` | int | 是 | 纯文本固定 `9999` |
| `cover` / `cover43` | string | 否 | 封面，不传由 B 站自动取 |
| `no_reprint` | int | 是 | `1` 不允许转载（自制稿件常用） |
| `is_only_self` | int | 否 | `1` 仅自己可见（不在正文里就不公开） |
| `dynamic` | string | 否 | 空间动态文案 |
| `recreate` | int | 是 | `-1` 允许二创 |
| `web_os` | int | 是 | 固定 `3` |
| `subtitle` | obj | 是 | `{"open": 0, "lan": ""}` |
| `interactive` / `act_reserve_create` / `no_disturbance` | int | 是 | 均为 `0` |
| `dolby` / `lossless_music` | int | 是 | 均为 `0` |
| `up_selection_reply` / `up_close_reply` / `up_close_danmu` | bool | 是 | 均为 `false` |

**`videos` 数组元素：**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `filename` | string | 是 | **预上传 `upos_uri` 的无后缀文件名**（无 `.mp4`） |
| `cid` | int | 是 | 预上传返回的 `biz_id` |
| `title` | string | 是 | 分 P 标题，最多 80 字符 |
| `desc` | string | 否 | 分 P 简介 |

**curl 示例：**

```bash
curl -X POST "https://member.bilibili.com/x/vu/web/add/v3?t=$(date +%s%3N)&csrf=${bili_jct}" \
  -H "Referer: https://member.bilibili.com/platform/upload/video/frame" \
  -H "Origin: https://member.bilibili.com" \
  -H "Content-Type: application/json" \
  -H "Cookie: SESSDATA=...; bili_jct=..." \
  -d '{
    "title": "示例标题",
    "tid": 21,
    "copyright": 2,
    "source": "原作者（TikTok @handle）",
    "tag": "直播回放,VTuber",
    "desc": "简介内容",
    "desc_format_id": 9999,
    "cover": "",
    "cover43": "",
    "recreate": -1,
    "no_disturbance": 0,
    "no_reprint": 1,
    "subtitle": {"open": 0, "lan": ""},
    "interactive": 0, "act_reserve_create": 0,
    "dolby": 0, "lossless_music": 0,
    "up_selection_reply": false, "up_close_reply": false, "up_close_danmu": false,
    "web_os": 3,
    "videos": [
      {"filename": "n260928ad1bz7vpwbo05fk28guzw96ul", "cid": 42272754632, "title": "分P 01", "desc": ""}
    ]
  }'
```

**响应：**

```json
{ "code": 0, "message": "0", "data": { "aid": 117347868284135, "bvid": "BV11Ca36sE35" } }
```

提交成功后稿件进审核，**立刻用 `x/web-interface/view` 查会返回 `-404`**，
要等过审（纯 ASCII 标题约 1 分钟）才可见。

---

### 3.6 编辑稿件 `POST /x/vu/web/edit`

修改已发布/草稿稿件。正文参数与 `add/v3` 基本一致，额外需要 `aid`：

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `aid` | int | 是 | 稿件 av 号 |
| `videos` | array | 是 | 分 P 数组（同 add） |

不更换视频文件时，`videos` 可传原文件信息或省略 `filename` 相关字段。

---

### 3.7 封面上传 `POST /x/vu/web/cover/up`

> 这个接口在 `live.py upload_cover()` 里已有可用实现（用于直播间封面），
> 投稿封面同样走它。**不是 multipart 上传文件**，而是把图片 base64 后放进
> 表单的 `cover` 字段；`live.py` 的实现可直接复用。

```
POST https://member.bilibili.com/x/vu/web/cover/up
Content-Type: application/x-www-form-urlencoded
```

| 表单字段 | 说明 |
|---|---|
| `cover` | `data:image/jpeg;base64,...`（图片内容 base64 的 data URI） |
| `csrf` | `bili_jct` Cookie 值 |

限制：≤10MB；jpg/png/webp（webp 需 Pillow 转码，见 `live.py`）。

**响应：**

```json
{ "code": 0, "data": { "url": "https://archive.biliimg.com/bfs/archive/xxxx.jpg" } }
```

注意字段名是 `url`（`cover_url` 是旧资料里的写法），填入 `add/v3` 的 `cover`。
投稿时这个参数可以整个省略，由 B 站自动取帧。

---

## 4. 分区 ID（tid）

获取方式：`POST https://member.bilibili.com/x/vupre/web/archive/types/predict`
（Cookie 鉴权，URL 带 `csrf`，正文 `filename` + `title`），`data` 返回 5 个候选子分区。
Web 端投稿页本身就是靠这个接口推荐分区，脚本照抄即可。

> 旧文档写的 `GET /x/web/archive/pre` 已于 2026-09 实测 404，`x/vupre/web/taxonomy`
> 等分区树接口同样失效；需要完整分区树时用社区维护的静态表。

录播/日常向常用子分区（2026-09 实测 `types/predict` 会优先推这些）：

| tid | 分区 |
|---|---|
| 21 | 生活 / 日常 |
| 27 | 动画 / 综合 |
| 65 | 游戏 / 网络游戏 |
| 138 | 生活 / 搞笑 |
| 254 | 生活 / 亲子 |

父分区（仅供定位）：动画 1 / 番剧 2 / 音乐 3 / 游戏 4 / 娱乐 5 / 知识 11 / 时尚 160。

标签可在投稿前校验可用性：`GET /x/vupre/web/topic/tag/check?tag=xxx`，
`code: 16025` 表示标签被封印。

---

## 5. 错误码速查

| code | 含义 | 处理建议 |
|---|---|---|
| 0 | 成功 | - |
| -101 | 账号未登录 | 检查 Cookie，重新 `live.py login` |
| -111 | CSRF 校验失败 | 核对 `bili_jct` 与 `csrf` |
| -352 | 风控校验失败 | 需 WBI 签名或人机验证，降低请求频率 |
| -400 | 请求参数错误 | 核对参数类型/必填项 |
| -403 | 权限不足 | 检查账号实名/创作者资格 |
| -404 | 接口不存在或**稿件未过审** | 前者确认路径；后者等审核（约 1 分钟） |
| -509 | 请求过于频繁 | 退避重试，控制并发 |
| 601 | **上传视频过快** | 连续提交约 10 个稿件触发，等十几分钟 |
| 16025 | 标签被封印 | 换标签 |

HTTP 403（上传阶段）：多为缺少 Cookie / Referer / UA 被风控。

**投稿频率限制**：Web 投稿接口连续提交约 10 个稿件会返回 601；此时网页端手动
上传可能要求短信验证。录播应合成 1 稿多分 P，而不是拆成几十个独立稿件。

---
## 6. 完整流程示例

仓库已实现本流程，**优先直接用 `bili/upload.py`**，不要照着文档手搓：

```bash
python3 upload.py status                                   # 先确认登录态
python3 upload.py --state s.json push <文件|目录>           # 传文件，不建稿件
python3 upload.py --state s.json post --title "标题" --tid 21 \
    --tag "a,b" --source "来源" --part-title-prefix "标题"
```

`upload.py` 覆盖了本文档全部步骤：预上传 → 登记 → 分片（并发 + 重试）→ 合并 →
提交稿件，并把每个文件的 `filename`/`cid` 存进 state JSON 以支持断点续传。

裸 bash 流程的坑（照着写容易踩）：

- 预上传响应**没有 `data` 包装层**，是扁平对象；
- `endpoint` 自带 `//`、`upos_uri` 自带 `upos://`，拼接时中间要补 `/`；
- 分片的 `chunk` 是**序号（从 0）**，`size` 是**本分片**字节数——旧资料写反了；
- 登记那步的 `uploads=` 等号不能漏，否则 404；
- 合并响应**没有 `filename` 字段**，要从 `upos_uri` 取无后缀名；
- 提交用 `/x/vu/web/add/v3`（JSON），不是已失效的 `/x/vu/client/add`（表单）。

---

## 7. 注意事项与风控

1. **登录态时效**：`SESSDATA` 有有效期，脚本化前先 `python3 upload.py status` 确认；
2. **请求头完整**：上传阶段缺 `Referer` / `UA` 极易触发 403；
3. **频率控制**：分片并发建议 ≤ 3（`--limit`），提交/编辑间隔 ≥ 1s，触发 `-509` 需退避；
4. **连续投稿限流**：约 10 个稿件触发 `code: 601`，网页端可能转为要短信验证；
5. **版权口径**：B 站明确「录制他人直播（包括授权录制）不属于自制内容，请选转载」——
   录播应投 `copyright=2` 并填 `source`，比标自制更安全，也避开标题被判冒充；
6. **审核延迟**：提交成功只代表进审核，`x/web-interface/view` 立刻查会 `-404`，
   纯 ASCII 标题约 1 分钟过审；含真实艺人名的标题可能被判疑似冒充而长期卡审；
7. **接口变更**：B 站接口会不定期调整路径或加参数，批量投稿前先小流量验证；
8. **竖屏投稿**：没有公开接口文档，主流实现（biliup-rs）也不支持，本文只覆盖普通稿件；
   竖屏片源走普通稿件播放时两侧会有黑边，内容不受影响；
9. **合规**：投稿需遵守 B 站社区规则与创作者协议，禁止用于刷量、侵权内容。

---

## 8. 参考资料

- [bilibili-API-collect](https://github.com/SocialSisterYi/bilibili-API-collect)（B 站接口逆向文档）
- [biliup / biliup-rs](https://github.com/biliup/biliup-rs)（上传流程参考实现）
