#!/usr/bin/env bash
# douyin/record.sh — 抖音录制入口（systemd / WebUI 使用）。
# 新架构：统一引擎 scripts/dlr.py（抖音解析复用 get_stream.py）。
#
# 用法： bash record.sh <web_rid|抖音号|URL> [--cookies FILE|--cookie HEADER]

if [ "$#" -lt 1 ]; then
    echo "用法：$0 <web_rid|抖音号|完整URL> [--cookies FILE|--cookie HEADER]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "${SCRIPT_DIR}/../scripts/dlr.py" douyin "$@"
