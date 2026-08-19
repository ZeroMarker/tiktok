#!/usr/bin/env bash
# tk/record.sh — TikTok 录制入口（systemd / WebUI 使用）。
# 新架构：统一引擎 scripts/dlr.py，本文件仅做转发。
#
# 用法： bash record.sh <tiktok_username>

if [ "$#" -lt 1 ]; then
    echo "用法：$0 <TikTok 用户名或直播URL>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "${SCRIPT_DIR}/../scripts/dlr.py" tiktok "$@"
