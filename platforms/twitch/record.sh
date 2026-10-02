#!/usr/bin/env bash
# Twitch 本地录制入口；转推 Bilibili 使用同目录 twitch.sh。

if [ "$#" -lt 1 ]; then
    echo "用法：$0 <Twitch 用户名或频道URL> [录制选项]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "${SCRIPT_DIR}/../../scripts/dlr.py" twitch "$@"
