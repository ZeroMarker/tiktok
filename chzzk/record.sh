#!/usr/bin/env bash
# chzzk/record.sh — CHZZK 录制入口（systemd / WebUI 使用）。
# 新架构：统一引擎 scripts/dlr.py。
#
# 用法： bash record.sh <频道ID或直播URL>

if [ "$#" -lt 1 ]; then
    echo "用法：$0 <CHZZK 频道ID或直播URL>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "${SCRIPT_DIR}/../scripts/dlr.py" chzzk "$@"
