#!/bin/bash

# 使用方法：
#   ./record.sh <web_rid|抖音号>
# 示例： ./record.sh 1234567890
# 示例： ./record.sh @zhangsan
# 示例： ./record.sh zhangsan

if [ $# -ne 1 ]; then
    echo "用法：$0 <抖音直播间 web_rid|抖音号>"
    echo "示例：$0 1234567890"
    echo "示例：$0 @zhangsan"
    exit 1
fi

INPUT="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"

sanitize_path_part() {
    printf '%s' "$1" | sed 's/[\/\\:*?"<>|]/_/g; s/^[[:space:]]*//; s/[[:space:]]*$//'
}

get_metadata_field() {
    local url="$1"
    local field="$2"
    yt-dlp --flat-playlist --no-warnings --skip-download --print "%(${field})s" "$url" 2>/dev/null | head -n1
}

get_nickname() {
    local url="$1"
    local value

    for field in channel uploader; do
        value=$(get_metadata_field "$url" "$field")
        if [ -n "$value" ] && [ "$value" != "NA" ]; then
            printf '%s' "$value"
            return 0
        fi
    done

    return 1
}

CLEAN_INPUT="${INPUT#@}"

# 先用直播房间 ID 尝试
DOUYIN_URL="https://live.douyin.com/${CLEAN_INPUT}"
echo "尝试作为直播房间 ID：${CLEAN_INPUT} ..."

ROOM_ID=$(yt-dlp --flat-playlist --no-warnings --skip-download --print "%(id)s" "$DOUYIN_URL" 2>/dev/null | head -n1)
if [ -z "$ROOM_ID" ]; then
    # 回退为抖音号
    DOUYIN_URL="https://www.douyin.com/user/${CLEAN_INPUT}"
    echo "未找到直播房间，回退为抖音号：${CLEAN_INPUT}"
else
    echo "确认为直播房间 ID：${ROOM_ID}"
fi

echo "正在获取抖音 ${CLEAN_INPUT} 的昵称..."
NICKNAME=$(get_nickname "$DOUYIN_URL")

if [ -n "$NICKNAME" ] && [ "$NICKNAME" != "NA" ]; then
    SAFE_NICKNAME=$(sanitize_path_part "$NICKNAME")
    RECORD_PREFIX="${CLEAN_INPUT}_${SAFE_NICKNAME}"
    OUTPUT_DIR="./${RECORD_PREFIX}"
else
    echo "未获取到昵称，输出目录将只使用输入标识。"
    RECORD_PREFIX="${CLEAN_INPUT}"
    OUTPUT_DIR="./${CLEAN_INPUT}"
fi

mkdir -p "$OUTPUT_DIR"
mkdir -p "$LOG_DIR"
cd "$OUTPUT_DIR" || exit 1

echo "开始无人值守录制抖音直播间 ${CLEAN_INPUT}"
echo "直播页：${DOUYIN_URL}"
echo "每 10 分钟生成一个 MP4 文件"
echo "输出目录：$(pwd)"
echo "按 Ctrl+C 停止，或用 kill 杀掉进程"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 尝试抓取直播源 ${CLEAN_INPUT} ..."

    STREAM_URL=$(yt-dlp "$DOUYIN_URL" --get-url 2>/dev/null | head -n1)

    if [ -z "$STREAM_URL" ]; then
        echo "  → 直播未开启 / 抓取失败，等待 60 秒后重试..."
        sleep 60
        continue
    fi

    echo "  → 成功抓到源：${STREAM_URL}..."
    echo "开始录制..."

    LOG_FILE="${LOG_DIR}/ffmpeg_record_${CLEAN_INPUT}_$(date +%Y%m%d).log"

    ffmpeg \
      -headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"$'\r\n'"Referer: https://www.douyin.com/"$'\r\n' \
      -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 -timeout 30000000 \
      -i "$STREAM_URL" \
      -c copy -bsf:a aac_adtstoasc \
      -map 0 -reset_timestamps 1 \
      -f segment \
      -segment_time 600 \
      -segment_format mp4 \
      -strftime 1 \
      "${RECORD_PREFIX}_%Y%m%d_%H%M%S.mp4" \
      2>> "$LOG_FILE" || echo "ffmpeg 异常退出（源可能已断），即将重试..."

    echo "录制中断，等待 10 秒后重新抓取源..."
    sleep 10
done
