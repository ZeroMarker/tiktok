#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [ "$(id -u)" -ne 0 ]; then
    echo "错误：请使用 sudo 运行此脚本。" >&2
    exit 1
fi
if ! [ -x /usr/sbin/logrotate ]; then
    echo "错误：请先安装 logrotate。" >&2
    exit 1
fi

# 自定义录制目录时传入与 WebUI 相同的 RECORDINGS_DIR。
if [ -z "${RECORDINGS_DIR:-}" ] && [ -f /etc/default/livestream-webui ]; then
    # 管理员维护的同一份配置；显式传入的目录优先。
    source /etc/default/livestream-webui
fi
RECORDINGS_DIR="${RECORDINGS_DIR:-$PROJECT_ROOT/recordings}"
LOG_USER="$(stat -c %U "$PROJECT_ROOT")"
LOG_GROUP="$(stat -c %G "$PROJECT_ROOT")"
install -d -o "$LOG_USER" -g "$LOG_GROUP" \
    "$PROJECT_ROOT/logs" "$PROJECT_ROOT/bili/logs" "$RECORDINGS_DIR/logs"
install -d /var/lib/logrotate

# 用 Python 逐字替换路径，避免 sed 对 &、反斜线等路径字符的解释。
python3 - "$PROJECT_ROOT" "$RECORDINGS_DIR" "$LOG_USER" "$LOG_GROUP" <<'PY'
import sys
from pathlib import Path

root, recordings, user, group = sys.argv[1:]
recordings = str(Path(recordings).resolve())
for value in (root, recordings):
    if any(c in value for c in '\n\r"$`\\'):
        raise SystemExit("日志路径含不支持的特殊字符")
text = (Path(root) / "systemd/livestream-logrotate.conf").read_text()
for key, value in (("PROJECT_ROOT", root), ("RECORDINGS_DIR", recordings),
                   ("LOG_USER", user), ("LOG_GROUP", group)):
    text = text.replace(f"__{key}__", value)
Path("/etc/livestream-logrotate.conf").write_text(text)
PY
chmod 644 /etc/livestream-logrotate.conf
/usr/sbin/logrotate --debug /etc/livestream-logrotate.conf
install -m 644 "$PROJECT_ROOT/systemd/livestream-logrotate.service" /etc/systemd/system/
install -m 644 "$PROJECT_ROOT/systemd/livestream-logrotate.timer" /etc/systemd/system/
systemctl daemon-reload
# 安装时只启用定时器，不强制轮转或额外删除现有日志。
systemctl enable --now livestream-logrotate.timer
