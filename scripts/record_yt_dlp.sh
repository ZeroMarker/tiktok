#!/usr/bin/env bash

set -u

if [ "$#" -ne 2 ]; then
    echo "内部用法：$0 <kick|youtube|chzzk> <用户名或直播URL>"
    exit 1
fi

PLATFORM="$1"
INPUT="$2"

for cmd in yt-dlp ffmpeg; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "错误：缺少依赖 $cmd"
        exit 1
    fi
done

case "$PLATFORM" in
    kick)
        IDENTIFIER=$(printf '%s' "$INPUT" | sed 's/[?#].*$//; s:/*$::; s:.*/::; s/^@//')
        LIVE_URL="https://kick.com/${IDENTIFIER}"
        REFERER="https://kick.com/"
        ;;
    youtube)
        if [[ "$INPUT" == http://* || "$INPUT" == https://* ]]; then
            LIVE_URL="$INPUT"
            IDENTIFIER=$(printf '%s' "$INPUT" | sed 's/[?#].*$//; s:/*$::; s:.*/::; s/^@//')
        else
            IDENTIFIER="${INPUT#@}"
            LIVE_URL="https://www.youtube.com/@${IDENTIFIER}/live"
        fi
        REFERER="https://www.youtube.com/"
        ;;
    chzzk)
        IDENTIFIER=$(printf '%s' "$INPUT" | sed 's/[?#].*$//; s:/*$::; s:.*/::; s/^@//')
        LIVE_URL="https://chzzk.naver.com/live/${IDENTIFIER}"
        REFERER="https://chzzk.naver.com/"
        ;;
    *)
        echo "错误：不支持的平台 $PLATFORM"
        exit 1
        ;;
esac

if [ -z "$IDENTIFIER" ]; then
    echo "错误：无法从输入中识别频道。"
    exit 1
fi

sanitize_path_part() {
    printf '%s' "$1" | sed 's/[\/\\:*?"<>|]/_/g; s/^[[:space:]]*//; s/[[:space:]]*$//'
}

CHANNEL_NAME=$(yt-dlp --no-warnings --skip-download --print '%(channel)s' "$LIVE_URL" 2>/dev/null | head -n1 || true)
if [ -z "$CHANNEL_NAME" ] || [ "$CHANNEL_NAME" = "NA" ]; then
    CHANNEL_NAME="$IDENTIFIER"
fi

SAFE_IDENTIFIER=$(sanitize_path_part "$IDENTIFIER")
SAFE_CHANNEL=$(sanitize_path_part "$CHANNEL_NAME")
RECORD_PREFIX="${PLATFORM}_${SAFE_IDENTIFIER}"
if [ "$SAFE_CHANNEL" != "$SAFE_IDENTIFIER" ]; then
    RECORD_PREFIX="${RECORD_PREFIX}_${SAFE_CHANNEL}"
fi

OUTPUT_ROOT="${RECORDINGS_DIR:-./recordings}"
OUTPUT_DIR="${OUTPUT_ROOT}/${RECORD_PREFIX}"
LOG_DIR="${OUTPUT_ROOT}/logs"
mkdir -p "$OUTPUT_DIR" "$LOG_DIR"

echo "开始无人值守录制 ${PLATFORM}：${IDENTIFIER}"
echo "输出目录：${OUTPUT_DIR}"
echo "每 10 分钟生成一个 MP4 文件"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 尝试获取直播源..."
    STREAM_URL=$(yt-dlp --no-warnings -f 'best[ext=mp4]/best' --get-url "$LIVE_URL" 2>/dev/null | head -n1 || true)

    if [ -z "$STREAM_URL" ]; then
        echo "  → 未开播或抓取失败，60 秒后重试..."
        sleep 60
        continue
    fi

    echo "  → 成功获取直播源，开始录制。"
    LOG_FILE="${LOG_DIR}/ffmpeg_${PLATFORM}_${SAFE_IDENTIFIER}_$(date +%Y%m%d).log"

    ffmpeg -nostdin \
      -fflags +discardcorrupt \
      -headers "User-Agent: Mozilla/5.0"$'\r\n'"Referer: ${REFERER}"$'\r\n' \
      -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 -rw_timeout 30000000 \
      -i "$STREAM_URL" \
      -c copy \
      -map 0:v:0 -map '0:a:0?' \
      -f segment -segment_time 600 -segment_format mp4 -reset_timestamps 1 -strftime 1 \
      "${OUTPUT_DIR}/${RECORD_PREFIX}_%Y%m%d_%H%M%S.mp4" \
      2>> "$LOG_FILE" || echo "ffmpeg 异常退出，即将重新获取直播源。"

    sleep 10
done
