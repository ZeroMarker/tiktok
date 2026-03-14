#!/bin/bash

USERNAME="$1"
if [ -z "$USERNAME" ]; then
    echo "用法: $0 <TikTok用户名>"
    exit 1
fi

# 移除之前的目录操作，直接在当前目录推流
echo "开始无人值守推流 TikTok @$USERNAME -> Bilibili"

while true; do
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 正在尝试获取直播源..."

    # 1. 动态抓取最新的 m3u8 地址
    STREAM_URL=$(yt-dlp --format "best" --get-url "https://www.tiktok.com/@${USERNAME}/live" 2>/dev/null | head -n1)

    if [ -z "$STREAM_URL" ]; then
        echo "  → 未监测到直播或抓取失败，60秒后重试..."
        sleep 60
        continue
    fi

    echo "  → 成功获取源，开始向 B 站推流..."

    # 2. 核心推流逻辑 (修复版 v3)
    # 修复点:
    # - 使用 setpts 滤镜重新生成视频时间戳
    # - 使用 aresample=async=1 重新生成音频时间戳
    # - 保持 48000Hz 音频采样率
    # - H.264 重新编码确保兼容性
    ffmpeg -re \
        -headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"$'\r\n'"Referer: https://www.tiktok.com/"$'\r\n' \
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
        "rtmp://live-push.bilivideo.com/live-bvc/?streamname=live_185817791_2793265&key=4d79bfae0b9b4488987e86e87a4444e1&schedule=rtmp&pflag=2" \
        2>> "ffmpeg_${USERNAME}_errors.log"

    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 推流中断，10秒后重新抓取..."
    sleep 10
done
