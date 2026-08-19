#!/bin/bash
#
# tk.sh — TikTok 录制兼容入口（保留旧接口 tk <username>）。
# 新架构：统一引擎 scripts/dlr.py，本文件仅做转发。
#
# 用法：
#   bash tk.sh <tiktok_username>     （直接运行）
#   source tk.sh && tk <username>    （source 用法）

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

tk() {
    python3 "${PROJECT_ROOT}/scripts/dlr.py" tiktok "$@"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [ $# -ne 1 ]; then
        echo "用法：$0 <TikTok 用户名>"
        echo "示例：$0 kobiritukii"
        exit 1
    fi
    tk "$1"
fi
