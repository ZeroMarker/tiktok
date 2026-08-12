#!/usr/bin/env bash

if [ "$#" -ne 1 ]; then
    echo "用法：$0 <CHZZK 频道ID或直播URL>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "${SCRIPT_DIR}/scripts/record_yt_dlp.sh" chzzk "$1"
