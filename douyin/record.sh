#!/bin/bash

# 使用方法：
#   ./record.sh <web_rid|抖音号|完整URL> [--cookies FILE|--cookie HEADER]
# 示例： ./record.sh 1930162853
# 示例： ./record.sh @zhangsan
# 示例： ./record.sh https://live.douyin.com/1234567890

set -e

if [ $# -lt 1 ]; then
    echo "用法：$0 <web_rid|抖音号|完整URL> [--cookies FILE|--cookie HEADER]"
    echo "示例：$0 1930162853"
    exit 1
fi

INPUT="$1"
shift
COOKIE_ARGS=("$@")
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${SCRIPT_DIR}/logs"
PY_GET_STREAM="${SCRIPT_DIR}/get_stream.py"

sanitize_path_part() {
    printf '%s' "$1" | sed 's/[\/\\:*?"<>|]/_/g; s/^[[:space:]]*//; s/[[:space:]]*$//'
}

CLEAN_INPUT="$(printf '%s' "$INPUT" | sed 's/[?#].*$//; s:/*$::; s:.*/::; s/^@//')"

if [ -z "$CLEAN_INPUT" ]; then
    echo "错误：无法从输入中识别直播间标识。"
    exit 1
fi

for cmd in python ffmpeg; do
    if ! command -v "$cmd" >/dev/null 2>&1; then
        echo "错误：缺少依赖 $cmd"
        exit 1
    fi
done

if [ ! -f "${SCRIPT_DIR}/DouyinLiveRecorder/src/spider.py" ]; then
    echo "错误：抖音解析子模块尚未初始化。"
    echo "请运行：git submodule update --init --recursive"
    exit 1
fi

# Get nickname
echo "正在获取昵称..."
NICKNAME=$(python "$PY_GET_STREAM" "$INPUT" "${COOKIE_ARGS[@]}" --get-nickname 2>/dev/null || true)

if [ -n "$NICKNAME" ]; then
    SAFE_NICKNAME=$(sanitize_path_part "$NICKNAME")
    RECORD_PREFIX="${CLEAN_INPUT}_${SAFE_NICKNAME}"
    OUTPUT_DIR="./${RECORD_PREFIX}"
    echo "昵称：${NICKNAME}"
else
    echo "未获取到昵称，输出目录将只使用输入标识。"
    RECORD_PREFIX="${CLEAN_INPUT}"
    OUTPUT_DIR="./${CLEAN_INPUT}"
fi

mkdir -p "$OUTPUT_DIR"
mkdir -p "$LOG_DIR"
cd "$OUTPUT_DIR" || exit 1

echo "开始无人值守录制抖音直播间 ${CLEAN_INPUT}"
echo "每 10 分钟生成一个 MP4 文件"
echo "输出目录：$(pwd)"
echo "按 Ctrl+C 停止，或用 kill 杀掉进程"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 尝试抓取直播源 ${CLEAN_INPUT} ..."

    STREAM_URL=$(python "$PY_GET_STREAM" "$INPUT" "${COOKIE_ARGS[@]}" --get-url 2>/dev/null || true)

    if [ -z "$STREAM_URL" ]; then
        echo "  → 直播未开启 / 抓取失败，等待 60 秒后重试..."
        sleep 60
        continue
    fi

    echo "  → 成功抓到源，开始录制..."

    LOG_FILE="${LOG_DIR}/ffmpeg_record_${CLEAN_INPUT}_$(date +%Y%m%d).log"

    ffmpeg \
      -headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"$'\r\n'"Referer: https://www.douyin.com/"$'\r\n' \
      -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 -rw_timeout 30000000 \
      -i "$STREAM_URL" \
      -c copy -bsf:a aac_adtstoasc \
      -map 0:v:0 -map '0:a:0?' -reset_timestamps 1 \
      -f segment \
      -segment_time 600 \
      -segment_format mp4 \
      -strftime 1 \
      "${RECORD_PREFIX}_%Y%m%d_%H%M%S.mp4" \
      2>> "$LOG_FILE" || echo "ffmpeg 异常退出（源可能已断），即将重试..."

    echo "录制中断，等待 10 秒后重新抓取源..."
    sleep 10
done
