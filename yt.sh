#!/bin/bash

# Load environment variables from ~/.bashrc
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi

USERNAME="$1"

if [ -z "$USERNAME" ]; then
    echo "用法：$0 <YouTube 頻道 handle 或 直播連結>"
    echo "範例:"
    echo "  $0 @PewDiePie          # 自動找 https://www.youtube.com/@PewDiePie/live"
    echo "  $0 https://www.youtube.com/@MrBeast/live"
    exit 1
fi

# 如果輸入不是完整網址，自動補成 YouTube 直播頁
if [[ "$USERNAME" == @* ]]; then
    YT_LIVE_URL="https://www.youtube.com/${USERNAME}/live"
else
    YT_LIVE_URL="$USERNAME"
fi

# Bilibili 推流地址
BILI_RTMP="${BILIBILI_PUSH_URL}${BILIBILI_PUSH_CODE}"

# 日志目录
LOG_DIR="./logs"
mkdir -p "$LOG_DIR"

echo "開始無人值守推流 YouTube 直播 ($YT_LIVE_URL) -> Bilibili"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 正在嘗試獲取直播源..."

    # 1. 抓取最新的直播 m3u8 網址（YouTube 直播常用 HLS）
    # --format best 通常會給最高品質的 HLS 連結
    # 如果失敗可改用 -f "bestvideo+bestaudio/best" 但通常 best 已足夠
    STREAM_URL=$(yt-dlp --get-url --format "best" "$YT_LIVE_URL" 2>/dev/null | head -n1)

    if [ -z "$STREAM_URL" ]; then
        echo " → 未偵測到直播或抓取失敗，60 秒後重試..."
        sleep 60
        continue
    fi

    echo " → 成功獲取源：$STREAM_URL"
    echo " → 開始向 B 站推流..."

    LOG_FILE="${LOG_DIR}/ffmpeg_youtube_$(date +%Y%m%d).log"

    # 2. 核心推流邏輯（保留你原來的優化設定）
    ffmpeg -re \
        -headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"$'\r\n'"Referer: https://www.youtube.com/"$'\r\n' \
        -fflags +genpts+igndts+discardcorrupt \
        -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 \
        -i "$STREAM_URL" \
        -vf "setpts=N/FRAME_RATE/TB" -r 25 \
        -c:v libx264 -preset ultrafast -tune zerolatency -b:v 2500k -maxrate 2500k -bufsize 5000k -g 50 \
        -c:a aac -b:a 128k -ar 48000 -ac 2 \
        -af "aresample=async=1" \
        -f flv \
        -flvflags no_duration_filesize \
        -max_muxing_queue_size 9999 \
        "$BILI_RTMP" \
        2>> "$LOG_FILE"

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 推流中斷，10 秒後重新抓取源..."
    sleep 10
done
