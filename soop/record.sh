#!/usr/bin/env bash
# soop/record.sh — SOOP 录制入口（systemd / WebUI 使用）。
# 新架构：统一引擎 scripts/dlr.py。
# 若项目根存在 soop-cookies.txt（Netscape 格式，SOOP 登录态），自动附带 --cookies，
# 以录制需要登录的会员订阅直播（live API RESULT=-6）。
#
# 用法： bash record.sh <soop_用户名或直播URL>

if [ "$#" -lt 1 ]; then
    echo "用法：$0 <SOOP 用户名或直播链接>"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_COOKIE="${SCRIPT_DIR}/../soop-cookies.txt"

# 依赖（yt-dlp 等）安装在开发用户的 ~/.local；服务可能以其他用户运行，
# 这里显式补充 PYTHONPATH / PATH，保证子进程 yt-dlp 能被找到。
for d in \
    "/home/ubuntu/.local/lib/python3.12/site-packages" \
    "$HOME/.local/lib/python3.12/site-packages" \
    "$HOME/.local/lib/python3.11/site-packages"; do
    if [ -d "$d" ] && [[ ":$PYTHONPATH:" != *":$d:"* ]]; then
        export PYTHONPATH="${d}${PYTHONPATH:+:$PYTHONPATH}"
    fi
done
for d in "$HOME/.local/bin" /home/ubuntu/.local/bin; do
    if [ -d "$d" ] && [[ ":$PATH:" != *":$d:"* ]]; then
        export PATH="$d:$PATH"
    fi
done

args=("$@")
# 未显式指定 --cookies/--cookie 且项目默认 cookie 存在时，自动附带
if [ -f "$DEFAULT_COOKIE" ] && ! printf '%s\n' "$@" | grep -qE -- '--cookies|--cookie '; then
    args+=(--cookies "$DEFAULT_COOKIE")
fi

exec python3 "${SCRIPT_DIR}/../scripts/dlr.py" soop "${args[@]}"
