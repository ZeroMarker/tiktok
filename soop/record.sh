#!/usr/bin/env bash
# soop/record.sh — SOOP 录制入口（systemd / WebUI 使用）。
# 新架构：统一引擎 scripts/dlr.py。
#
# 用法： bash record.sh <soop_用户名或直播URL>

if [ "$#" -lt 1 ]; then
    echo "用法：$0 <SOOP 用户名或直播链接>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "${SCRIPT_DIR}/../scripts/dlr.py" soop "$@"
