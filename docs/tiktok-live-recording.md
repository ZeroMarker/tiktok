# TikTok 直播录制使用与排障说明

## 当前入口

日常录制统一使用：

```bash
bash /root/tiktok/tk/record.sh <username>
```

`tk.sh`、`fallback_tk.sh` 仅作为旧接口兼容保留；其余历史调试脚本（`tk_direct.sh`、`playwright_*.py`、`fallback_tk2/3.sh` 等）已移除。不要仅凭 Web API 的 GroupBlock 或离线结果判定无法录制；应首先直接运行正式入口，让引擎轮询实际流地址。

> 适用环境：Linux（root），ffmpeg ≥ 6.1，yt-dlp 已安装
> 最后更新：2026-08-13

## 1. 概述

正式入口为 `tk/record.sh`：

| 架构 | 说明 |
|------|------|
| `scripts/dlr.py` | 统一录制引擎（所有平台共用） |
| `scripts/dlr/adapters/tiktok.py` | TikTok 适配器：yt-dlp → impersonate → mobile → curl_cffi 四方法兜底 |
| `tk/record.sh` | TikTok 转发入口（调用引擎） |
| `tk.sh` / `fallback_tk.sh` | 旧接口兼容 |

两个脚本均实现**无人值守自动录制**：检测到直播开播即录，断流自动重连，每 10 分钟切一个 MP4 分段。

## 2. 快速开始

```bash
bash /root/tiktok/tk/record.sh hana_kuraki87
```

⚠️ 脚本会长期占用终端，**必须在 tmux / zellij 新窗口中运行**，不要在当前会话直接执行：

```bash
tmux new -s tk_hana
bash /root/tiktok/tk/record.sh hana_kuraki87
# 退出窗口：Ctrl+B 然后 D（detach），录制继续后台运行
```

停止录制：回到该 tmux 窗口按 `Ctrl+C`，或 `tmux kill-session -t tk_hana`。

## 3. 工作原理

主循环流程：

```
获取主播昵称 → 确定输出目录（user_nickname）
   ↓
┌─────────────────────────────┐
│ yt-dlp 抓取 FLV 直播流地址    │
│  └─ 失败 → 等 60s → 重试      │
│  └─ 成功 → ffmpeg 分段录制    │
│        └─ 断流/异常退出        │
│              → 等 10s → 重试   │
└─────────────────────────────┘
```

- 主播没开播时：每 60 秒探测一次，直到抓到流
- 录制中断流：每 10 秒重试抓源，直播恢复后自动续录
- 全程无需人工干预，适合整夜无人值守

## 4. 输出结构

在**执行脚本时的当前目录**下生成（脚本内含 `cd`，之后相对路径均相对输出目录）：

```
./hana_kuraki87_華夏/                  ← 输出目录：用户名_昵称
    hana_kuraki87_20260811_183000.mp4  ← 10 分钟一个分段
    hana_kuraki87_20260811_184000.mp4
./logs/
    ffmpeg_record_hana_kuraki87_20260811.log  ← 当日 ffmpeg 日志
```

- 目录命名失败（没抓到昵称）时退化为 `./<username>`
- 分段文件名：`<用户名>_<日期>_<起始时间>.mp4`，时间戳从 0 开始

## 5. 关键参数说明

| 参数 | 作用 |
|------|------|
| `-f "b[ext=flv]"` | 强制选 FLV 流。HLS 流 token 短会导致只录十几秒就断，FLV 可长期稳定录制 |
| `-fflags +discardcorrupt` | 丢弃损坏数据包，防止 FLV 流坏包导致 ffmpeg 退出 |
| `-map 0:v -map 0:a` | 只保留音视频，跳过字幕流（MP4 容器不支持） |
| `-live_start_index -1` | 从最新 GOP 开始，加快直播拉起速度 |
| `-f segment -segment_time 600` | 分段输出，每 10 分钟一个 MP4 |
| `-c copy -bsf:a aac_adtstoasc` | 流复制不转码，音频转换 ADTS→ASC 适配 MP4 |
| `-reset_timestamps 1` | 每段时间戳从 0 开始 |
| `-rw_timeout 30000000` | 读写超时 30s（微秒），网络卡死时自动断开重连 |
| `-reconnect 1 -reconnect_streamed 1` | 流式断线自动重连 |

## 6. 常见问题与排障

### 6.1 ffmpeg 报 `Option timeout not found`（2026-08-11 根因）

**现象**：ffmpeg 拒录，日志持续报错。

**根因**：`-timeout` 不是 http/https 协议的合法 ffmpeg 选项，只对直接 tcp 路径生效；流经 tls 层或 HTTP CONNECT 代理时选项被丢弃，直接报错退出。

**解决**：使用正式入口 `tk/record.sh`，其中已改用 `-rw_timeout`（AVFormatContext 原生读写超时选项，对所有协议生效）。

### 6.2 代理导致全部请求失败

**现象**：clash 停止或代理失效后，走代理的旧会话所有请求指向死端口，一直"抓取失败"。

**解决**：先检查当前代理环境；不要把一次 Web API 失败直接解释为直播不可录制，应让正式入口的 `live_check.py` 兜底继续轮询。

### 6.3 一直显示"直播未开启 / 抓取失败"

**可能原因**：
- 主播确实没在播 —— 正常，脚本每 60s 自动重试，无需干预
- 网络/代理问题 —— 见 §6.2
- 检测失效 —— 见 §6.7

**运维判断**：会话日志中连续多行"直播未开启/抓取失败"且长时间无 ffmpeg 输出，说明只是空轮询，可清理该 tmux 会话避免占用。

### 6.4 ffmpeg 异常退出后反复重试

**现象**：日志出现 "ffmpeg 异常退出（源可能已断）"。

**处理**：脚本会自动等 10s 重试，一般无需干预。若连续多次失败，检查：
- 直播是否真的结束（看直播页面）
- 抓到的流地址是否有效（`yt-dlp --get-url` 手工验证）
- 代理/网络（§6.2）

### 6.5 只录了十几秒就断

**原因**：抓到了 HLS 流，token 短导致录几分钟就失效。

**解决**：确认抓流命令带 `-f "b[ext=flv]"` 强制 FLV。若某主播无 FLV 流，需另想办法（暂未内置）。

### 6.6 报 `TNS_Host_GroupBlock_LCC_DSA_V1`

**现象**：yt-dlp/ffmpeg 拉流被拒，报 IP 地理封锁。

**原因**：TikTok 对部分区域 IP 限制直播流。

**解决**：换日本等地区服务器/VPN 出口，或手动获取直链流地址喂给 ffmpeg。

### 6.7 yt-dlp 报 "not currently live" 但主播实际在播

**现象**：确认主播在播，但 yt-dlp 抓不到流（webcast room/info 返回 4003110 等）。

**原因**：TikTok 检测接口对无登录 Cookie 的请求限流/风控。

**解决**（备选方向）：
- 给 yt-dlp 配登录 Cookie
- 换用 webcast API 直接解析
- 用 Playwright 渲染页面拿 LiveRoomInfo
- 直接用备用脚本，见 §7

## 7. 辅助工具链（/root/tiktok/tk/）

排障与备用检测工具集中在 `/root/tiktok/tk/`（脚本目录，可正常访问）：

| 文件 | 说明 |
|------|------|
| `tk/record.sh` | TikTok 转发入口 → 统一引擎 `scripts/dlr.py` |
| `scripts/dlr/adapters/tiktok.py` | TikTok 适配器（含 4 方法兜底检测） |
| `tk/live_check.py` | curl_cffi 直接解析页面 + webcast API，取流地址（引擎的兜底方法） |
| `tk.sh` / `fallback_tk.sh` | 旧接口兼容入口 |

**live_check.py 单独使用**（yt-dlp 失败时二次确认）：

```bash
python3 /root/tiktok/tk/live_check.py <username>
# 成功 → stdout 输出一行流 URL；失败 → exit 1
```

## 8. 运维速查

```bash
# 查看正在录制的会话
tmux ls

# 查看某会话日志（确认是否真在录，而非空轮询）
# 日志在"执行脚本时的当前目录"下的 logs/，例如从 ~/scripts 执行则为 ~/scripts/logs/
tail -f ./logs/ffmpeg_record_<user>_$(date +%Y%m%d).log

# 停止录制
tmux kill-session -t <session名>

# 手工验证主播是否在播、能否抓到流
yt-dlp "https://www.tiktok.com/@<user>/live" -f "b[ext=flv]" --get-url
```

## 9. 注意事项

- 不要用 `find`/`grep` 扫描 `/root/tiktok` 目录（约 14GB，会卡死）；但 `/root/tiktok/tk/` 是脚本目录（见 §7），不受此限制
- 日常功能应优先合入并测试 `tk/record.sh`；备用脚本只保留平台兼容实验，不作为默认入口
- 涉及脚本改动用 git 确认版本、`git diff` 对比后再动
