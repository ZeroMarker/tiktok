#!/bin/bash
#
# record.sh — TikTok 直播录制的标准入口（systemd / WebUI 使用）。
#
# 全部实现已收敛到 lib.sh，本文件仅加载并调用 record_live。
#
# 使用方法：
#   bash record.sh <tiktok_username>
# 示例： bash record.sh kobiritukii

# shellcheck source=tk/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [ $# -ne 1 ]; then
        echo "用法：$0 <TikTok 用户名>"
        echo "示例：$0 kobiritukii"
        exit 1
    fi
    record_live "$1"
fi
