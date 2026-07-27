#!/bin/bash
#
# fallback_tk.sh — TikTok 直播录制备用脚本
#
# 当主脚本 (tk.sh) 对特定主播反复返回"直播未开启"时使用。
# 在 yt-dlp 失败时，用 Python (curl_cffi) 直接解析页面 SIGI_STATE
# 二次确认直播状态，避免误判。
#
# === 与 tk.sh 的差异 ===
# - yt-dlp 失败后用 Python 脚本 live_check.py 做二次检测
# - 支持多次重试（retry loop），每次刷新页面和 Cookie
# - 所有 fallback 方法按优先级依次尝试
#
# 使用方法：
#   source ~/tiktok/tk/fallback_tk.sh
#   tk_fallback <tiktok_username>
#
# 或在 tmux/zellij 中直接运行：
#   bash ~/tiktok/tk/fallback_tk.sh <username>
#
# 示例：
#   tk_fallback emma_kusunoki
#   bash ~/tiktok/tk/fallback_tk.sh shibuya_kaho
#
# 依赖：
#   pip install curl_cffi
#   yt-dlp >= 2026.06.09

SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIVE_CHECK_PY="${SCRIPTS_DIR}/live_check.py"

sanitize_path_part() {
    printf '%s' "$1" | sed 's/[\/\\:*?"<>|]/_/g; s/^[[:space:]]*//; s/[[:space:]]*$//'
}

get_metadata_field() {
    local url="$1"
    local field="$2"
    yt-dlp --flat-playlist --no-warnings --skip-download --print "%(${field})s" "$url" 2>/dev/null | head -n1
}

get_nickname() {
    local url="$1"
    local value
    for field in channel uploader; do
        value=$(get_metadata_field "$url" "$field")
        if [ -n "$value" ] && [ "$value" != "NA" ]; then
            printf '%s' "$value"
            return 0
        fi
    done
    return 1
}

# --- 检测方法优先级 ---

# 方法1: yt-dlp 默认（带 --impersonate）
try_ytdlp_default() {
    local username="$1"
    yt-dlp "https://www.tiktok.com/@${username}/live" \
        -f "b[ext=flv]" --impersonate chrome --get-url 2>/dev/null | head -n1
}

# 方法2: yt-dlp + --xff US（伪造地理位置）
try_ytdlp_xff() {
    local username="$1"
    yt-dlp "https://www.tiktok.com/@${username}/live" \
        -f "b[ext=flv]" --impersonate chrome --xff US --get-url 2>/dev/null | head -n1
}

# 方法3: yt-dlp + mobile 域名
try_ytdlp_mobile() {
    local username="$1"
    yt-dlp "https://m.tiktok.com/@${username}/live" \
        -f "b[ext=flv]" --impersonate chrome --get-url 2>/dev/null | head -n1
}

# 方法4: Python fallback (curl_cffi 解析 SIGI_STATE)
try_python_fallback() {
    local username="$1"
    if [ -f "$LIVE_CHECK_PY" ]; then
        python3 "$LIVE_CHECK_PY" "$username" 2>/dev/null
    fi
}

# --- 主函数 ---

tk_fallback() {
    if [ $# -ne 1 ]; then
        echo "用法：tk_fallback <TikTok 用户名>"
        echo "示例：tk_fallback emma_kusunoki"
        return 1
    fi

    local USERNAME="$1"
    local LOG_DIR="./logs"
    local MAX_ATTEMPTS=20   # 最多尝试 20 次（约 20 分钟）
    local RETRY_INTERVAL=60  # 每次间隔 60 秒

    echo "正在获取 TikTok @${USERNAME} 的昵称..."
    local NICKNAME=$(get_nickname "https://www.tiktok.com/@${USERNAME}")

    local RECORD_PREFIX
    local OUTPUT_DIR

    if [ -n "$NICKNAME" ] && [ "$NICKNAME" != "NA" ]; then
        local SAFE_NICKNAME=$(sanitize_path_part "$NICKNAME")
        RECORD_PREFIX="${USERNAME}_${SAFE_NICKNAME}"
        OUTPUT_DIR="./${RECORD_PREFIX}"
    else
        RECORD_PREFIX="${USERNAME}"
        OUTPUT_DIR="./${USERNAME}"
    fi

    mkdir -p "$OUTPUT_DIR"
    mkdir -p "$LOG_DIR"
    cd "$OUTPUT_DIR" || return 1

    echo "开始无人值守录制 TikTok @$USERNAME (备用模式)"
    echo "输出目录：$(pwd)"
    echo "检测方法优先级: yt-dlp > yt-dlp+xff > yt-dlp+mobile > Python fallback"
    echo ""

    local STREAM_URL=""
    local attempt=1

    while [ -z "$STREAM_URL" ]; do
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 尝试 #${attempt}: 检测直播源 @${USERNAME} ..."

        # 按优先级依次尝试各方法
        STREAM_URL=$(try_ytdlp_default "$USERNAME")
        [ -n "$STREAM_URL" ] && echo "  → 方法1(yt-dlp) 成功" && break

        STREAM_URL=$(try_ytdlp_xff "$USERNAME")
        [ -n "$STREAM_URL" ] && echo "  → 方法2(yt-dlp+xff) 成功" && break

        STREAM_URL=$(try_ytdlp_mobile "$USERNAME")
        [ -n "$STREAM_URL" ] && echo "  → 方法3(mobile) 成功" && break

        STREAM_URL=$(try_python_fallback "$USERNAME")
        [ -n "$STREAM_URL" ] && echo "  → 方法4(Python fallback) 成功" && break

        # 所有方法失败，等待重试
        if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
            echo "  → 已达到最大尝试次数 (${MAX_ATTEMPTS})，退出"
            echo "  → 建议：手动确认 @${USERNAME} 是否在直播，或增大 MAX_ATTEMPTS"
            return 1
        fi

        echo "  → 所有方法均未检测到直播，${RETRY_INTERVAL}s 后重试..."
        sleep "$RETRY_INTERVAL"
        ((attempt++))
    done

    echo "  → 成功抓到源：${STREAM_URL:0:80}..."
    echo "开始录制..."

    local LOG_FILE="../${LOG_DIR}/ffmpeg_record_${USERNAME}_$(date +%Y%m%d).log"

    ffmpeg -nostdin \
      -fflags +discardcorrupt \
      -headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"$'\r\n'"Referer: https://www.tiktok.com/"$'\r\n' \
      -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 -timeout 30000000 \
      -i "$STREAM_URL" \
      -c copy -bsf:a aac_adtstoasc \
      -map 0:v -map 0:a -live_start_index -1 \
      -f segment \
      -segment_time 600 \
      -segment_format mp4 \
      -reset_timestamps 1 \
      -strftime 1 \
      "${RECORD_PREFIX}_%Y%m%d_%H%M%S.mp4" \
      2>> "$LOG_FILE" || echo "ffmpeg 异常退出（源可能已断），即将重试..."

    echo "录制中断，等待 10 秒后重新检测..."
    sleep 10
    # 重新检测（while true 循环）
    exec "$0" "$USERNAME"
}

# 如果直接运行脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [ $# -ne 1 ]; then
        echo "用法：$0 <TikTok 用户名>"
        echo "示例：$0 emma_kusunoki"
        exit 1
    fi
    tk_fallback "$1"
fi
