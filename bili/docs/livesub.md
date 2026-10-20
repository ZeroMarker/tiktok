# 实验：直播转推实时字幕（livesub.py）

> **状态（2026-10-20）：自动推流流程仍暂停接入，支持手动测试。** `push.sh`、WebUI 值守和
> systemd 单元都不调用 `livesub.py`。本地方案的暂停原因见[结论](#结论)；
> 阿里云方案的录像推流测试见 [2026-10-20 测试记录](livesub-aliyun-test-20261020.md)。

`bili/livesub.py` 把 TikTok 直播转推到 B 站，同时用本地模型识别日语、用本地或云端翻译成中文，
烧进画面。

## 流程

```
TikTok FLV ─ ffmpeg(取流, -re) ─┬─ -c copy → MPEG-TS 管道 → 延迟缓冲 N 秒 → ffmpeg(drawtext + x264) → B 站 RTMP
                                └─ 16 kHz f32 音频 → Nemotron 流式 ASR → 切句 → Hy-MT2 翻译 → 字幕文件
```

- **语音识别**：Nemotron 3.5 streaming 0.6B Q8_0，通过 transcribe.cpp Python 绑定常驻加载。
  命令行版每次调用都要重新加载模型，约 6 秒，不适合实时。
  需要共享库构建 `~/.local/share/tube-asr/transcribe.cpp/build-shared/`（`-DTRANSCRIBE_BUILD_SHARED=ON`）。
- **切句**：该模型只在停顿处提交文本，连续说话时全部停留在 tentative。
  脚本对 committed + tentative 全文自行切句：
  - 在标点处切，且一句至少 10 字；末尾 3 字可能被改写，不参与断句；
  - 超过 28 字强制切；
  - 文本停止变化 1.5 秒（且够长）或 3.5 秒时切。
- **翻译**：本地 llama-server（`127.0.0.1:18091`）加载 Hy-MT2-1.8B Q4_K_M。提示词：
  - 带一句上文，用官方「背景信息」模板；
  - 术语表 `bili/livesub-glossary.tsv` 中命中的条目用官方「参考下面的翻译」模板注入；
  - 带上文时译文明显过长，就去掉上文重译（模型偶尔把上文一起译出来）；
  - 不足 5 字的片段不带上文（否则会回显模板标签），不超过 2 字的片段不翻译。
- **对齐**：画面经缓冲延迟 `--delay` 秒，默认 5 秒（2026-10-20 调整）；字幕更新按「出现时刻 + delay」排期。
  字幕整体在画面上方居中，距画面顶部 120 像素；字幕块内上行是实时日文，
  下行是最近一句中文，6 秒无更新清屏。
  5 秒是后续试跑起点，尚未完成端到端验证；当前脚本仍使用本地 Hy-MT2，
  其历史慢请求可能超过 5 秒，必要时用 `--delay` 调大。

部署细节见 `~/tube/docs/nemotron-asr-linux.md`、`~/tube/docs/hy-mt2-test.md`。

云端翻译备选：[阿里云机器翻译](aliyun-translation.md) 已接入本脚本的手动测试入口
`--mt-backend aliyun`；默认仍为本地 Hy-MT2。自动推流流程仍不调用本脚本。

## 用法

```bash
# llama-server 需先启动
~/.local/share/hy-mt/llama.cpp/build/bin/llama-server \
  -m ~/.local/share/hy-mt/models/Hy-MT2-1.8B-Q4_K_M.gguf -c 2048 -t 2 --host 127.0.0.1 --port 18091 &

python3 bili/livesub.py <tiktok用户名> --out /tmp/test.flv --duration 90    # 写本地文件
python3 bili/livesub.py <tiktok用户名> --out rtmp                           # 推 push.env 中的 B 站地址
python3 bili/livesub.py x --source 录制文件.mp4 --out /tmp/t.flv            # 用录制文件离线测试

# 阿里云翻译：先在交互式 Bash 加载已 export 的凭据，再用录像实时测试
source ~/.bashrc
python3 bili/livesub.py x --source 录制文件.mp4 --out /tmp/aliyun.flv \
  --duration 90 --delay 5 --mt-backend aliyun --workdir /tmp/livesub-aliyun
# --out rtmp 可改为实际推 B 站，需先开播、同步推流码并确保没有其他推流进程。
```

云端后端目前固定日译中，只接受 `--language ja-JP`；不使用本地提示词和术语表，
单次请求超时为 5 秒，失败跳过该句。工作目录保存转写 TSV、字幕文本及
`push-progress.log`（FFmpeg 帧数、输出时间、速度）；日志中的“字幕晚于排期”表示
翻译与队列等待已超过设定的视频缓冲，不包含 ASR 自身的识别延迟。

推 B 站前需先开播（`live.py start`），并把新推流码写入 `~/.config/bili/push.env`。
注意：`live.py start --print-export` 打印的推流码是打码占位符，不能直接写入；
真实推流码在 `~/.config/bili/accounts/live.json` 的 `rtmp_code` 字段里。

## 测试记录（2026-10-16～17）

机器为 4 核 Neoverse-N1、24 GB 内存。每项只跑了一次。

| 主播 | 延迟 | 方式 | 翻译句数 | 翻译耗时 平均 / 最长 | 超过延迟 | 整机 CPU | 结果 |
|---|---|---|---:|---|---:|---:|---|
| marumo_rea | 3 s | 推 B 站 5 分钟 | 76 | 约 1.2 s / 4.6 s | — | — | 正常 |
| marumo_rea（录制） | 3 s | 本地 2 分钟 | 26 | 1.5 s / 6.7 s | — | 64% | 正常 |
| ena.satsuki | 3 s | 推 B 站 3 分钟 | 22 | 4.5 s / 10.6 s | 多句 | 74% | 中文常晚于画面 |
| ena.satsuki | 10 s | 推 B 站 3 分钟 | 21 | 2.9 s / 4.9 s | 0 | 74% | 正常 |
| tubasa___mai | 10 s | 推 B 站 3 分钟 | 14 | 11.8 s / 19.8 s | 9 | 约 99% | **推流中断** |
| tubasa___mai | 10 s | 推 B 站 3 分钟 | 38 | 4.9 s / 17.5 s | 1 | 97% | 正常 |
| tubasa___mai | 10 s | 本地 3 分钟 | 50 | 3.5 s / 6.3 s | 0 | 91% | 正常 |

**推流中断那次**：同机有 HyperFrames 自动视频任务（`~/daily`）。它跑了 3 个 whisper-cli 进程，
负载升到 16.5；取流落后达 58 秒，编码推流的 ffmpeg 因 Broken pipe 退出。
脚本不会自动重启推流，所以中断后直到手动重启都没有画面。

### 资源占用（tubasa___mai，本地输出 3 分钟，机器基本空闲）

开始前负载 2.15，结束时 1 分钟负载升到 8.15。各进程 %CPU 为 16 次采样均值，100% = 1 核：

| 组件 | CPU | 内存 |
|---|---:|---:|
| 翻译（llama-server，2 线程） | 116% | 3.0 GB |
| 编码（ffmpeg 解码 + drawtext + x264 veryfast） | 106% | 0.15 GB |
| 语音识别（Nemotron，2 线程） | 93% | 1.2 GB |
| **合计** | **约 3.1 核** | **约 4.4 GB** |

说话少的主播（marumo_rea、ena.satsuki，每 3 分钟约 20 句）合计约 2–2.4 核；
说话密的主播翻译量翻倍，翻译占到 1.2 核以上。

### 翻译质量

- 识别正确的句子大意基本可用，例如
  「あら強がっちゃう後輩がいるのね」→「真有那种故意装酷的后辈呢」。
- 识别错误会被按字面硬译，例如
  - 「土地感ない」（应为 土地勘）→「对土地的感受也消失了」；
  - 「ハンマ湯です馬器です」→「锤子汤，一种器具」。
- 人名、作品名、品牌常被音译错，例如「レイバン」→「雷本」、「アルジーさん」→「阿尔吉女士」。
  ASR 不支持热词，术语表只能作用于翻译这一侧。
- 切句仍会在词中间断开（如「出 / たやつ」），两半分别翻译后意思会乱。
- 带一句上文只带来小幅改善（如「許せん」→「不允许」），翻译每句平均多约 0.5 秒。

## 结论

暂不接入推流流程：

1. **资源不够**：一路字幕推流占 2–3 核（共 4 核）。同机任何重任务都会让它卡顿或中断，
   也无法同时跑两路。
2. **质量不够**：字幕底稿受 ASR 错误限制，翻译不能纠错，需要人工校对级别的质量才适合公开直播。
3. **延迟代价**：当时为让字幕跟上画面，把直播延迟设为 10 秒；密集说话测试仍出现过超时。

## 若以后重启

可尝试的方向：

- **降低负载**：
  - x264 改 `superfast`，约省 0.3 核；
  - 翻译改 1 线程，约省 0.5 核，10 秒缓冲能容纳变慢的翻译；
  - 把翻译和编码固定在不同核上。
- **稳定性**：给编码推流 ffmpeg 加自动重启，参照 `push.sh` 的看门狗；
  给 `~/daily` 等批处理任务加 `nice`。
- **质量**：
  - 按主播维护术语表（常提到的人名、作品名）；
  - 用 YouTube 字幕流程那样的 LLM 翻译替代 Hy-MT2（见 `~/tube/docs/hy-mt2-test.md` 结论）。
