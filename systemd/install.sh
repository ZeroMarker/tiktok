#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ "$(id -u)" -ne 0 ]; then
    echo "错误：请使用 sudo 运行此脚本。"
    exit 1
fi

install -d -m 755 "$PROJECT_ROOT/recordings" "$PROJECT_ROOT/logs" "$PROJECT_ROOT/state"
sed "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
    "$PROJECT_ROOT/systemd/livestream-webui.service" \
    > /etc/systemd/system/livestream-webui.service
chmod 644 /etc/systemd/system/livestream-webui.service

# 录制控制面（引擎宿主）：与 WebUI 分离，重启 UI 不再打断录制（ADR 0002）。
sed "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
    "$PROJECT_ROOT/systemd/livestream-recorderd.service" \
    > /etc/systemd/system/livestream-recorderd.service
chmod 644 /etc/systemd/system/livestream-recorderd.service

# 共享浏览器渲染服务：所有录制引擎复用一个常驻 Chromium（CDP），
# 消除每轮探测冷启动浏览器的开销（见 scripts/dlr/browserd.py）。
sed "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" \
    "$PROJECT_ROOT/systemd/tiktok-browserd.service" \
    > /etc/systemd/system/tiktok-browserd.service
chmod 644 /etc/systemd/system/tiktok-browserd.service

# 认证已移除：WebUI 仅面向内网/隧道/受控反代。如需认证请先启用 server.py 中的校验。
# 该环境文件由 WebUI 与 recorderd 共用（见文件内注释）。
if [ ! -e /etc/default/livestream-webui ]; then
    install -m 600 /dev/null /etc/default/livestream-webui
    printf '%s\n' \
      'LIVE_WEBUI_HOST=127.0.0.1' \
      'LIVE_WEBUI_PORT=8766' \
      "RECORDINGS_DIR=$PROJECT_ROOT/recordings" \
      > /etc/default/livestream-webui
fi

bash "$PROJECT_ROOT/systemd/install-logrotate.sh"
systemctl daemon-reload

# 升级路径（旧版 WebUI 自己托管引擎）：必须先停 UI 再起引擎宿主，
# 否则两边会同时录制同一频道（重复分段、双写同一输出目录）。
systemctl stop livestream-webui.service 2>/dev/null || true
systemctl enable --now livestream-recorderd.service
systemctl enable --now livestream-webui.service
systemctl enable --now tiktok-browserd.service

systemctl --no-pager --full status livestream-recorderd.service | head -8
systemctl --no-pager --full status livestream-webui.service | head -8
echo "录制控制面（引擎宿主）：$PROJECT_ROOT/state/run/recorderd.sock"
echo "WebUI 后端已启动：http://127.0.0.1:8766"
echo "可使用 Caddy 将公网入口反向代理到该地址。"
