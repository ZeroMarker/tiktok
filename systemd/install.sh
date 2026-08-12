#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ "$(id -u)" -ne 0 ]; then
    echo "错误：请使用 sudo 运行此脚本。"
    exit 1
fi

install -d -m 755 "$PROJECT_ROOT/recordings" "$PROJECT_ROOT/logs"
install -m 644 "$PROJECT_ROOT/systemd/livestream-webui.service" /etc/systemd/system/livestream-webui.service

if [ ! -e /etc/default/livestream-webui ]; then
    TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    install -m 600 /dev/null /etc/default/livestream-webui
    printf '%s\n' \
      'LIVE_WEBUI_HOST=127.0.0.1' \
      'LIVE_WEBUI_PORT=8766' \
      "LIVE_WEBUI_TOKEN=$TOKEN" \
      "RECORDINGS_DIR=$PROJECT_ROOT/recordings" \
      > /etc/default/livestream-webui
    echo "访问令牌：$TOKEN"
fi

systemctl daemon-reload
systemctl enable --now livestream-webui.service
echo "WebUI 后端已启动：http://127.0.0.1:8766"
echo "可使用 Caddy 将公网入口反向代理到该地址。"
