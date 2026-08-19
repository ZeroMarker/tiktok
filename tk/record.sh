#!/usr/bin/env bash
# tk/record.sh — TikTok 录制入口（systemd / WebUI 使用）。
# 新架构：统一引擎 scripts/dlr.py，本文件做转发。
# 若项目根存在已登录的 cookies.txt，则自动附带登录态（部分主播需登录才能拿流）。
#
# 用法： bash record.sh <tiktok_username> [--cookies file ...]

if [ "$#" -lt 1 ]; then
    echo "用法：$0 <TikTok 用户名或直播URL> [--cookies file]"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DEFAULT_COOKIE="${SCRIPT_DIR}/../cookies.txt"

# 依赖（yt-dlp/curl_cffi 等）安装在开发用户的 ~/.local；服务可能以其他用户运行，
# 这里显式补充 PYTHONPATH / PATH，保证子进程 yt-dlp 能 import yt_dlp 并找到 curl_cffi。
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
# 未显式指定 --cookies/--cookie 且项目默认 cookie 存在时，自动附带（dlr 会透传给 yt-dlp）
if [ -f "$DEFAULT_COOKIE" ] && ! printf '%s\n' "$@" | grep -qE -- '--cookies|--cookie '; then
    args+=(--cookies "$DEFAULT_COOKIE")
fi

exec python3 "${SCRIPT_DIR}/../scripts/dlr.py" tiktok "${args[@]}"
