#!/bin/bash
set -uo pipefail

# Load environment variables from ~/.bashrc (参考 push.sh)
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi

# =============================================================================
# 用法说明
# =============================================================================
if [ -z "$1" ]; then
    echo "用法：$0 <Twitch 频道用户名 或 完整 URL>"
    echo "示例："
    echo "  $0 shroud"
    echo "  $0 https://www.twitch.tv/shroud"
    echo "  $0 xqc"
    exit 1
fi

# 输入处理：如果是完整 URL，只取用户名部分；如果是纯用户名，直接用
INPUT="$1"
if [[ "$INPUT" == *"twitch.tv/"* ]]; then
    TWITCH_USERNAME=$(echo "$INPUT" | sed 's|.*/||' | sed 's|[?#].*||')
else
    TWITCH_USERNAME="$INPUT"
fi

TWITCH_URL="https://www.twitch.tv/$TWITCH_USERNAME"

# Bilibili 推流地址 (参考 push.sh: BILIBILI_PUSH_URL + BILIBILI_PUSH_CODE)
BILI_RTMP="${BILIBILI_PUSH_URL}${BILIBILI_PUSH_CODE}"

# =============================================================================
# 依赖检查
# =============================================================================
for cmd in yt-dlp ffmpeg; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "错误：缺少依赖 $cmd"
        echo "请安装："
        echo "  yt-dlp （推荐最新 nightly 版：yt-dlp --update-to nightly）"
        echo "  ffmpeg"
        exit 1
    fi
done

# 日志目录
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"

# =============================================================================
# 信号处理：优雅退出
# =============================================================================
FFMPEG_PID=""
cleanup() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 收到退出信号，正在清理..."
    [ -n "$FFMPEG_PID" ] && kill "$FFMPEG_PID" 2>/dev/null
    pkill -P $$ ffmpeg 2>/dev/null || true
    echo "清理完成，脚本退出。"
    exit 0
}
trap cleanup SIGINT SIGTERM SIGQUIT

# =============================================================================
# 主程序开始
# =============================================================================
echo "===================================================="
echo "无人值守推流：Twitch @$TWITCH_USERNAME → Bilibili"
echo "频道 URL: $TWITCH_URL"
echo "B 站推流地址：${BILI_RTMP:0:50}..."
echo "按 Ctrl+C 停止"
echo "===================================================="

while true; do
    TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$TIMESTAMP] 正在尝试获取直播源..."

    # 获取 Twitch 直播 m3u8 地址（优先 best 质量）
    STREAM_URL=$(yt-dlp --no-warnings -f "best" --get-url "$TWITCH_URL" 2>&1 | grep -v "^\[" | tail -n1)

    if [ -z "$STREAM_URL" ] || [[ "$STREAM_URL" == *"ERROR"* || "$STREAM_URL" == *"No video"* || "$STREAM_URL" == *"is offline"* ]]; then
        echo " → 未检测到直播 / 抓取失败（频道未开播、地区限制或 yt-dlp 需要更新），60秒后重试..."
        sleep 60
        continue
    fi

    echo " → 成功获取源：${STREAM_URL:0:100}..."

    echo " → 开始向 Bilibili 推流..."

    LOG_FILE="\( {LOG_DIR}/ffmpeg_twitch_ \){TWITCH_USERNAME}_$(date +%Y%m%d).log"

    # ffmpeg 推流核心命令（优化参数组合）
    ffmpeg -y \
        -headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"\( '\r\n'"Referer: https://www.twitch.tv/" \)'\r\n' \
        -timeout 60000000 \
        -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 10 -reconnect_on_network_error 1 \
        -i "$STREAM_URL" \
        \
        -vf "fps=30,setpts=N/30/TB" \
        -r 30 \
        \
        -c:v libx264 -preset veryfast -tune zerolatency \
        -b:v 2500k -maxrate 2800k -bufsize 5000k \
        -g 120 -keyint_min 60 \
        -profile:v main -level 4.0 \
        -pix_fmt yuv420p \
        \
        -c:a aac -b:a 128k -ar 48000 -ac 2 \
        -af "aresample=async=1:first_pts=0" \
        \
        -f flv \
        -flvflags no_duration_filesize \
        -max_muxing_queue_size 9999 \
        -bsf:v h264_mp4toannexb \
        -fflags +genpts+igndts+discardcorrupt \
        "$BILI_RTMP" \
        2>> "$LOG_FILE" &

    FFMPEG_PID=$!

    wait "$FFMPEG_PID"
    EXIT_CODE=$?
    FFMPEG_PID=""

    if [ $EXIT_CODE -eq 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 推流正常结束"
    elif [ $EXIT_CODE -eq 137 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 推流进程被杀死（可能是内存不足 OOM）"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 推流中断（退出码 $EXIT_CODE），查看日志：$LOG_FILE"
    fi

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 10秒后重新尝试抓取源..."
    sleep 10
done
