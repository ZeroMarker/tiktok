#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "用法：$0 <chrome|chromium|edge|firefox|brave|opera|vivaldi|safari> [输出文件]"
    exit 1
fi

if ! command -v yt-dlp >/dev/null 2>&1; then
    echo "错误：缺少依赖 yt-dlp"
    exit 1
fi

BROWSER="$1"
OUTPUT_FILE="${2:-./douyin-cookies.txt}"
OUTPUT_DIR=$(dirname "$OUTPUT_FILE")
mkdir -p "$OUTPUT_DIR"

if ! yt-dlp \
  --cookies-from-browser "$BROWSER" \
  --cookies "$OUTPUT_FILE" \
  --skip-download \
  "https://www.douyin.com/" >/dev/null 2>&1; then
    # yt-dlp may reject the Douyin homepage after it has already exported
    # the browser cookie jar. Only fail when no cookie file was produced.
    if [ ! -s "$OUTPUT_FILE" ]; then
        echo "错误：无法从 $BROWSER 导出 Cookie，请确认浏览器已安装且已登录抖音。"
        exit 1
    fi
fi

chmod 600 "$OUTPUT_FILE"
echo "Cookie 已导出到：$OUTPUT_FILE"
echo "录制时使用：bash douyin/record.sh <直播间> --cookies '$OUTPUT_FILE'"
