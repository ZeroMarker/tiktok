#!/usr/bin/env bash

set -euo pipefail

if [ $# -ne 1 ]; then
    echo "用法：$0 <TikTok 用户名或直播 URL>"
    echo "示例：$0 kobiritukii"
    echo "示例：$0 https://www.tiktok.com/@kobiritukii/live"
    exit 1
fi

INPUT="$1"

if [[ "$INPUT" == http://* || "$INPUT" == https://* ]]; then
    LIVE_URL="$INPUT"
else
    USERNAME="${INPUT#@}"
    LIVE_URL="https://www.tiktok.com/@${USERNAME}/live"
fi

echo "检测直播源：$LIVE_URL"
yt-dlp "$LIVE_URL" --get-url


