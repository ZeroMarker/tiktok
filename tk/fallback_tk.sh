#!/bin/bash
#
# fallback_tk.sh — 备用模式入口（保留原 tk_fallback 接口）。
# 实现在 lib.sh。备用的多方法检测（yt-dlp/impersonate/mobile/Python curl_cffi）
# 现在是统一实现的一部分，不再单独维护一套逻辑。
#
# 使用方法：
#   bash fallback_tk.sh <tiktok_username>

# shellcheck source=tk/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# 保持旧的 tk_fallback() 接口不变
tk_fallback() {
    record_live "$@"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [ $# -ne 1 ]; then
        echo "用法：$0 <TikTok 用户名>"
        echo "示例：$0 emma_kusunoki"
        exit 1
    fi
    tk_fallback "$1"
fi
