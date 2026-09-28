#!/bin/bash

# Load environment variables from ~/.bashrc
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi

USERNAME="${1:-}"
if [ -z "$USERNAME" ]; then
    echo "用法：$0 <TikTok 用户名>"
    exit 1
fi

for cmd in yt-dlp ffmpeg python3; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "错误：缺少依赖 $cmd"
        exit 1
    fi
done

# WebUI 管理的推流配置优先于旧的 ~/.bashrc 导出项。
if [ -f "$HOME/.config/bili/push.env" ]; then
    source "$HOME/.config/bili/push.env"
fi

if [ -z "${BILIBILI_PUSH_URL:-}" ] || [ -z "${BILIBILI_PUSH_CODE:-}" ]; then
    # 非交互 shell 下 ~/.bashrc 头部会提前 return，兜底直读其中的导出项（同 replay.sh）
    eval "$(grep -E '^export BILIBILI_PUSH_(URL|CODE)=' ~/.bashrc 2>/dev/null)" || true
fi
if [ -z "${BILIBILI_PUSH_URL:-}" ] || [ -z "${BILIBILI_PUSH_CODE:-}" ]; then
    echo "错误：请先设置 BILIBILI_PUSH_URL 和 BILIBILI_PUSH_CODE"
    exit 1
fi

# Bilibili 推流地址
BILI_RTMP="${BILIBILI_PUSH_URL}${BILIBILI_PUSH_CODE}"

# 日志目录
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "开始无人值守推流 TikTok @$USERNAME -> Bilibili"

# 输入无数据 N 秒则报错退出（微秒）；输出侧卡死由下面的看门狗兜底
RW_TIMEOUT_US=15000000
# ffmpeg 日志超过 N 秒无输出即判假死（正常推流时 progress 每秒多行）
STALL_TIMEOUT=60

FFMPEG_PID=""
cleanup() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 收到退出信号，清理进程..."
    [ -n "$FFMPEG_PID" ] && kill "$FFMPEG_PID" 2>/dev/null || true
    pkill -P $$ ffmpeg 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM SIGQUIT

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 正在尝试获取直播源..."

    # 1. 取流（统一走 get_stream.py：yt-dlp www/m 子域 × impersonate 逐级试，
    #    不行再 curl_cffi 直解页面 + webcast API；与 webui 验流同链路）
    PROBE_LOG="${LOG_DIR}/yt-dlp_${USERNAME}_$(date +%Y%m%d).log"
    STREAM_URL=$(python3 "$SCRIPT_DIR/get_stream.py" "$USERNAME" 2>>"$PROBE_LOG" | head -n1)

    if [ -z "$STREAM_URL" ]; then
        echo "  → 未监测到直播或抓取失败（详见 $PROBE_LOG），60 秒后重试..."
        sleep 60
        continue
    fi

    echo "  → 成功获取源，开始向 B 站推流..."

    LOG_FILE="${LOG_DIR}/ffmpeg_tiktok_${USERNAME}_$(date +%Y%m%d).log"

    # 2. 核心推流逻辑 (修复版 v5)
    # v4 修复点（2026-09-08 实测：TikTok 源 EOF 重连后 ffmpeg 假死 8 分钟不退不报错）：
    # - 输入加 -rw_timeout：源端断流 15s 直接报错退出，外层重抓（此前无限挂起）
    # - 加日志看门狗：ffmpeg 日志 60s 无输出即 kill 重推（此前只管退出不管卡死）
    # - 输出 30fps：-g 60 保持 2s GOP
    # - 加 -pix_fmt yuv420p：源为 yuvj420p 全范围，转限范围防偏色（同 replay.sh）
    # - 加 -reconnect_at_eof/-reconnect_on_network_error：EOF/TLS 错误也自动重连
    #
    # v5 修复点（2026-09-28 实测：B 站推流音画不同步）：
    # 起因是 v3/v4 的 `setpts=N/FRAME_RATE/TB` + `-r 30`。它用滤镜帧计数器 N 和
    # 容器*声明*的 r_frame_rate 重建视频时间戳，而不是源的真实时间轴：
    #   1) 源是真 VFR。实测 240s 源流前 80s 为 25fps，之后掉到 15fps 到底，而
    #      r_frame_rate/avg_frame_rate 仍写 25。setpts 按 25 打戳，把 240s 的
    #      视频压进 4535/25=181.4s，直接丢掉 58.7s。
    #   2) 更致命：t≈93.4s 处源流降帧率重起 GOP，滤镜图被重新初始化，N 归零，
    #      setpts 的时间戳当场倒回 0，而音频继续往前走。实测 240s 源推完后
    #      视频时间轴只到 93.4s、音频到 240.0s，差 146.6s 且视频在 93s 后停住。
    # 音频侧 `aresample=async=1` 只对音频自己的时间戳做补偿，ffmpeg 没有跨流
    # 同步机制，两条时间轴各走各的，偏差只增不减。
    # 改为 `-vf fps=30`：按输入真实时间戳做 CFR 转换（丢/补帧到 30fps），
    # 保留真实时长，滤镜图重初始化也不会回卷。同一条源复测漂移 +0.25s
    # （≈源自身尾部误差，全程锁定）。
    # 另：输入去掉 igndts（FLV 无 PTS，igndts 会让 B 帧 PTS=DTS 而打乱显示
    # 顺序，fps 滤镜依赖真实时间戳）；输出加 first_pts=0 把音频起点也钉到 0
    # （同 twitch.sh）。
    ffmpeg -re \
        -headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"$'\r\n'"Referer: https://www.tiktok.com/"$'\r\n' \
        -fflags +discardcorrupt \
        -rw_timeout "$RW_TIMEOUT_US" \
        -analyzeduration 5M -probesize 5M \
        -reconnect 1 -reconnect_at_eof 1 -reconnect_streamed 1 -reconnect_on_network_error 1 -reconnect_delay_max 5 \
        -i "$STREAM_URL" \
        -vf "fps=30" \
        -c:v libx264 -preset ultrafast -tune zerolatency -b:v 2500k -maxrate 2500k -bufsize 5000k -g 60 -pix_fmt yuv420p \
        -c:a aac -b:a 128k -ar 48000 -ac 2 \
        -af "aresample=async=1:first_pts=0" \
        -f flv \
        -flvflags no_duration_filesize \
        -max_muxing_queue_size 9999 \
        "$BILI_RTMP" \
        2>> "$LOG_FILE" &
    FFMPEG_PID=$!

    # 看门狗：日志停滞即假死，杀掉重推
    while kill -0 "$FFMPEG_PID" 2>/dev/null; do
        sleep 15
        kill -0 "$FFMPEG_PID" 2>/dev/null || break
        NOW=$(date +%s)
        MTIME=$(stat -c %Y "$LOG_FILE" 2>/dev/null || echo "$NOW")
        if [ $((NOW - MTIME)) -ge "$STALL_TIMEOUT" ]; then
            echo "[$(date '+%Y-%m-%d %H:%M:%S')] ffmpeg ${STALL_TIMEOUT}s 无输出（假死），杀掉重推..."
            kill -KILL "$FFMPEG_PID" 2>/dev/null || true
            break
        fi
    done
    wait "$FFMPEG_PID"
    EXIT_CODE=$?
    FFMPEG_PID=""

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 推流中断（退出码 $EXIT_CODE），10 秒后重新抓取..."
    sleep 10
done
