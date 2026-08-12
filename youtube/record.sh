#!/usr/bin/env bash

if [ "$#" -ne 1 ]; then
    echo "用法：$0 <YouTube handle或直播URL>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "${SCRIPT_DIR}/scripts/record_yt_dlp.sh" youtube "$1"
