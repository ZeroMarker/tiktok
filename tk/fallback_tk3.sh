#!/usr/bin/env bash
# fallback_tk3.sh — 修复版备用录制（2026-08-04 14:50 UTC+8）
# 问题: live_check.py 现在直接输出 URL 字符串（如 HLS 地址），而 fallback_tk2.sh
#       的 fetch_stream_url 只解析以 "{" 开头的 dict 行，导致一直误报"直播未开启"。
# 修复: fetch_stream_url 改为内嵌 python，直接解析页面 roomId -> webcast API，
#       优先取 flv_pull_url.HD1（FLV 直链），回退 rtmp/hls；输出兼容 dict 行和 URL 行。
# 用法: bash fallback_tk3.sh <TikTok 用户名>
# 输出: /root/.nanobot/workspace/<username>_<nickname>/ 每10分钟一个MP4

set -u
USERNAME="${1:?用法: $0 <TikTok 用户名>}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
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
  # 内嵌 python: 页面 roomId -> webcast room/info -> 优先 FLV 直链
  python3 - "$USERNAME" <<'PYEOF'
import sys, re
from curl_cffi import requests

username = sys.argv[1]
s = requests.Session()
s.get("https://www.tiktok.com", impersonate="chrome131")
try:
    r = s.get(f"https://www.tiktok.com/@{username}/live", impersonate="chrome131", timeout=20)
except Exception:
    sys.exit(1)

room_ids = set(re.findall(r'"roomId":"(\d+)"', r.text))
for rid in room_ids:
    if not rid or rid == "0":
        continue
    try:
        p = s.get("https://webcast.tiktok.com/webcast/room/info/",
                  params={"room_id": rid, "aid": "1988"},
                  impersonate="chrome131", timeout=15)
        d = p.json()
    except Exception:
        continue
    data = d.get("data") or {}
    if data.get("status") != 2:
        continue
    su = data.get("stream_url") or {}
    flv = su.get("flv_pull_url") or {}
    url = (flv.get("HD1") or flv.get("SD1")
           or su.get("rtmp_pull_url") or su.get("hls_pull_url"))
    if url:
        print(url)
        sys.exit(0)
sys.exit(1)
PYEOF
}

echo "正在获取 TikTok @${USERNAME} 的昵称..."
NICKNAME=$(get_nickname)
RECORD_DIR="$OUT_DIR/${USERNAME}_${NICKNAME}"
mkdir -p "$RECORD_DIR"
echo "开始无人值守录制 TikTok @${USERNAME} (备用模式3)"
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
