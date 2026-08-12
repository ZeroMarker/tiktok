#!/usr/bin/env bash
# fallback_tk2.sh — 改进版备用录制（2026-08-04）
# 问题: live_check.py 新版 webcast API 的 stream_url 返回整个 dict（含 flv_pull_url），
#       fallback_tk.sh 直接把 dict 当 URL 传给 ffmpeg 导致失败。
# 修复: 用 python 从 dict 中提取 flv_pull_url.HD1 / rtmp_pull_url，再交给 ffmpeg。
# 用法: bash fallback_tk2.sh <TikTok 用户名>
# 输出: /root/.nanobot/workspace/<username>_<nickname>/ 每10分钟一个MP4

set -u
USERNAME="${1:?用法: $0 <TikTok 用户名>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIVE_CHECK_PY="$SCRIPT_DIR/live_check.py"
OUT_DIR="/root/.nanobot/workspace"
NICKNAME=""

get_nickname() {
  local nick
  nick=$(curl -s --max-time 15 "https://www.tiktok.com/@${USERNAME}" \
    -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/134.0.0.0 Safari/537.36" \
    | grep -oP '(?<="uniqueId":"'"${USERNAME}"'","nickname":")[^"]+' | head -1)
  [ -n "$nick" ] && echo "$nick" || echo "$USERNAME"
}

fetch_stream_url() {
  # 提取 stdout 里最后一行 python dict 中的 flv_pull_url.HD1 或 rtmp_pull_url
  python3 -c '
import sys, ast
raw = sys.stdin.read().strip()
if not raw:
    sys.exit(1)
# stdout 可能有多行，取最后一个看起来是 dict 的行
lines = [l for l in raw.splitlines() if l.startswith("{")]
if not lines:
    sys.exit(1)
try:
    d = ast.literal_eval(lines[-1])
except Exception:
    sys.exit(1)
url = None
if isinstance(d, dict):
    flv = d.get("flv_pull_url") or {}
    url = flv.get("HD1") or flv.get("SD1") or d.get("rtmp_pull_url") or d.get("hls_pull_url")
if url:
    print(url)
    sys.exit(0)
sys.exit(1)
' < <(python3 "$LIVE_CHECK_PY" "$USERNAME" 2>/dev/null)
}

echo "正在获取 TikTok @${USERNAME} 的昵称..."
NICKNAME=$(get_nickname)
RECORD_DIR="$OUT_DIR/${USERNAME}_${NICKNAME}"
mkdir -p "$RECORD_DIR"
echo "开始无人值守录制 TikTok @${USERNAME} (备用模式2)"
echo "输出目录：$RECORD_DIR"

LOG_FILE="$RECORD_DIR/ffmpeg_record_${USERNAME}_$(date +%Y%m%d).log"

while true; do
  STREAM_URL=$(fetch_stream_url)
  if [ -z "$STREAM_URL" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 直播未开启 / 抓取失败，等待 60 秒后重试..."
    sleep 60
    continue
  fi
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] 成功抓到直播源。"
  echo "开始录制..."
  ffmpeg -nostdin \
    -fflags +discardcorrupt \
    -headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"$'\r\n'"Referer: https://www.tiktok.com/"$'\r\n' \
    -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 -rw_timeout 30000000 \
    -i "$STREAM_URL" \
    -c copy -bsf:a aac_adtstoasc \
    -map 0:v -map 0:a -live_start_index -1 \
    -f segment \
    -segment_time 600 \
    -segment_format mp4 \
    -reset_timestamps 1 \
    -strftime 1 \
    "$RECORD_DIR/${USERNAME}_%Y%m%d_%H%M%S.mp4" \
    2>> "$LOG_FILE"
  echo "ffmpeg 退出（源可能已断），等待 10 秒后重新检测..."
  sleep 10
done
