#!/bin/bash

# 使用方法：
#   ./record_tiktok.sh <tiktok_username>
# 示例： ./record_tiktok.sh kobiritukii

if [ $# -ne 1 ]; then
    echo "用法：$0 <TikTok 用户名>"
    echo "示例：$0 kobiritukii"
    exit 1
fi

USERNAME="$1"
OUTPUT_DIR="./tiktok_records_${USERNAME}"   # 每个账号用独立文件夹，避免混在一起
LOG_DIR="./logs"

mkdir -p "$OUTPUT_DIR"
mkdir -p "$LOG_DIR"
cd "$OUTPUT_DIR" || exit 1

echo "开始无人值守录制 TikTok @$USERNAME"
echo "每 10 分钟生成一个 MP4 文件"
echo "输出目录：$(pwd)"
echo "按 Ctrl+C 停止，或用 kill 杀掉进程"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 尝试抓取直播源 @${USERNAME} ..."

    # 抓取直播 m3u8 地址（只取第一行，避免多行干扰）
    STREAM_URL=$(yt-dlp "https://www.tiktok.com/@${USERNAME}/live" --get-url 2>/dev/null | head -n1)

    if [ -z "$STREAM_URL" ]; then
        echo "  → 直播未开启 / 抓取失败，等待 60 秒后重试..."
        sleep 60
        continue
    fi

    echo "  → 成功抓到源：${STREAM_URL}..."   # 只显示前 80 字符，避免日志太长

    echo "开始录制..."

    LOG_FILE="../${LOG_DIR}/ffmpeg_record_${USERNAME}_$(date +%Y%m%d).log"

    ffmpeg \
      -headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"$'\r\n'"Referer: https://www.tiktok.com/"$'\r\n' \
      -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 -timeout 30000000 \
      -i "$STREAM_URL" \
      -c copy -bsf:a aac_adtstoasc \
      -map 0 -reset_timestamps 1 \
      -f segment \
      -segment_time 600 \
      -segment_format mp4 \
      -strftime 1 \
      "${USERNAME}_%Y%m%d_%H%M%S.mp4" \
      2>> "$LOG_FILE" || echo "ffmpeg 异常退出（源可能已断），即将重试..."

    echo "录制中断，等待 10 秒后重新抓取源..."
    sleep 10
done
