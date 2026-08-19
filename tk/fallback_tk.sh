#!/bin/bash
#
# fallback_tk.sh — TikTok 备用模式入口（保留旧接口 tk_fallback <username>）。
# 新架构：统一引擎 scripts/dlr.py 已内置多方法兜底检测（yt-dlp→impersonate→mobile→curl_cffi），
# 本文件仅做转发，不再单独维护一套备用逻辑。
#
# 用法：
#   bash fallback_tk.sh <tiktok_username>

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

tk_fallback() {
    python3 "${PROJECT_ROOT}/scripts/dlr.py" tiktok "$@"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [ $# -ne 1 ]; then
        echo "用法：$0 <TikTok 用户名>"
        echo "示例：$0 emma_kusunoki"
        exit 1
    fi
    tk_fallback "$1"
fi
