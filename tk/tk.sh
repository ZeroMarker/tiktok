#!/bin/bash
#
# tk.sh — 兼容入口（保留原名 tk 函数供习惯用法）。
# 实现在 lib.sh，此处仅保持旧接口：source 后调用 tk <username>。
#
# 使用方法：
#   source ~/scripts/tk.sh   （或 bash tk.sh）
#   tk <tiktok_username>

# shellcheck source=tk/lib.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib.sh"

# 保持旧的 tk() 接口不变，内部复用统一实现
tk() {
    record_live "$@"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [ $# -ne 1 ]; then
        echo "用法：$0 <TikTok 用户名>"
        echo "示例：$0 kobiritukii"
        exit 1
    fi
    tk "$1"
fi
