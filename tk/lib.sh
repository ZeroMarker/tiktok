#!/bin/bash
#
# lib.sh — TikTok 直播录制的共享实现库。
#
# 收敛了分散在 record.sh / tk.sh / fallback_tk.sh 里的重复逻辑：
#   - 路径清洗、昵称抓取
#   - 多方法流检测（yt-dlp → impersonate → mobile → Python curl_cffi）
#   - ffmpeg 分段录制（含 SIGTERM 优雅停止 trap）
#   - 无人值守主循环
#
# 使用：source tk/lib.sh 后调用 record_live <username>
# 依赖：yt-dlp、ffmpeg、python3（含 curl_cffi，见 live_check.py）

# 本文件所在目录（用于定位 live_check.py）
SCRIPTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 录制控制参数（可通过环境变量覆盖）
: "${RECORD_SEGMENT_SECONDS:=600}"   # 每段 MP4 时长（秒）
: "${RECORD_RETRY_SECONDS:=60}"      # 未开播时的重试间隔（秒）
: "${RECORD_BREAK_SECONDS:=10}"      # 断流后重新抓取的间隔（秒）

sanitize_path_part() {
    printf '%s' "$1" \
      | tr -d '[:cntrl:]' \
      | sed 's/[\/\\:*?"<>|]/_/g; s/^[[:space:].]*//; s/[[:space:].]*$//' \
      | cut -c1-120
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

# --- 流检测：按优先级依次尝试，输出一行流 URL（stdout） ---
try_stream_ytdlp() {
    local username="$1" url="$2" fmt="$3"
    yt-dlp "$url" -f "b[ext=flv]/best${fmt}" --get-url 2>/dev/null | head -n1
}

detect_stream() {
    local username="$1"
    local url=""

    # 方法1: yt-dlp https 主域
    url=$(try_stream_ytdlp "$username" "https://www.tiktok.com/@${username}/live" "")
    [ -n "$url" ] && { echo "$url"; return 0; }

    # 方法2: yt-dlp + impersonate chrome
    url=$(yt-dlp "https://www.tiktok.com/@${username}/live" -f "b[ext=flv]/best" --impersonate chrome --get-url 2>/dev/null | head -n1)
    [ -n "$url" ] && { echo "$url"; return 0; }

    # 方法3: yt-dlp mobile 子域
    url=$(yt-dlp "https://m.tiktok.com/@${username}/live" -f "b[ext=flv]/best" --impersonate chrome --get-url 2>/dev/null | head -n1)
    [ -n "$url" ] && { echo "$url"; return 0; }

    # 方法4: Python (curl_cffi) 直接解析页面 —— 解决 yt-dlp 被风控误判"未开播"
    if [ -f "${SCRIPTS_DIR}/live_check.py" ]; then
        echo "  → yt-dlp 均失败，尝试 Python 备用方案 (curl_cffi) ..." >&2
        url=$(python3 "${SCRIPTS_DIR}/live_check.py" "$username" 2>/dev/null | head -n1)
        [ -n "$url" ] && { echo "$url"; return 0; }
    fi

    return 1
}

# --- ffmpeg 分段录制（后台 + SIGTERM 优雅停止，避免残留孤儿进程） ---
record_ffmpeg() {
    local username="$1"
    local rec_prefix="$2"
    local log_dir="$3"
    local stream_url="$4"

    local log_file="../${log_dir}/ffmpeg_record_${username}_$(date +%Y%m%d).log"
    local ffmpeg_pid rc

    ffmpeg -nostdin \
      -fflags +discardcorrupt \
      -headers "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"$'\r\n'"Referer: https://www.tiktok.com/"$'\r\n' \
      -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 -rw_timeout 30000000 \
      -i "$stream_url" \
      -c copy -bsf:a aac_adtstoasc \
      -map 0:v:0 -map '0:a:0?' -reset_timestamps 1 \
      -f segment \
      -segment_time "$RECORD_SEGMENT_SECONDS" \
      -segment_format mp4 \
      -strftime 1 \
      "${rec_prefix}_%Y%m%d_%H%M%S.mp4" \
      2>> "$log_file" &
    ffmpeg_pid=$!

    # 优雅停止：SIGTERM/SIGINT 时先结束 ffmpeg 再退出；配合单元 KillMode=mixed 与 TimeoutStopSec
    trap 'kill "$ffmpeg_pid" 2>/dev/null; wait "$ffmpeg_pid" 2>/dev/null; echo "收到停止信号，已停止录制。"; exit 0' TERM INT

    wait "$ffmpeg_pid"
    rc=$?
    trap - TERM INT
    if [ "$rc" -ne 0 ]; then
        echo "ffmpeg 异常退出（源可能已断），即将重试..."
    fi
    return "$rc"
}

# --- 无人值守主循环 ---
record_live() {
    if [ $# -ne 1 ]; then
        echo "用法：record_live <TikTok 用户名>"
        echo "示例：record_live kobiritukii"
        return 1
    fi

    for cmd in yt-dlp ffmpeg python3; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            echo "错误：缺少依赖 $cmd"
            return 1
        fi
    done

    local USERNAME="${1#@}"
    USERNAME=$(sanitize_path_part "$USERNAME")
    if [ -z "$USERNAME" ]; then
        echo "错误：用户名无效。"
        return 1
    fi

    local LOG_DIR="./logs"

    echo "正在获取 TikTok @${USERNAME} 的昵称..."
    local NICKNAME
    NICKNAME=$(get_nickname "https://www.tiktok.com/@${USERNAME}" || true)

    local RECORD_PREFIX
    local OUTPUT_DIR
    if [ -n "$NICKNAME" ] && [ "$NICKNAME" != "NA" ]; then
        local SAFE_NICKNAME
        SAFE_NICKNAME=$(sanitize_path_part "$NICKNAME")
        RECORD_PREFIX="${USERNAME}_${SAFE_NICKNAME}"
        OUTPUT_DIR="./${RECORD_PREFIX}"
    else
        echo "未获取到昵称，输出目录将只使用 username。"
        RECORD_PREFIX="${USERNAME}"
        OUTPUT_DIR="./${USERNAME}"
    fi

    mkdir -p "$OUTPUT_DIR"
    mkdir -p "$LOG_DIR"
    cd "$OUTPUT_DIR" || return 1

    echo "开始无人值守录制 TikTok @$USERNAME"
    echo "每 $RECORD_SEGMENT_SECONDS 秒生成一个分段"
    echo "输出目录：$(pwd)"

    while true; do
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 尝试抓取直播源 @${USERNAME} ..."

        local STREAM_URL
        STREAM_URL=$(detect_stream "$USERNAME") || true

        if [ -z "$STREAM_URL" ]; then
            echo "  → 直播未开启 / 抓取失败，等待 $RECORD_RETRY_SECONDS 秒后重试..."
            sleep "$RECORD_RETRY_SECONDS"
            continue
        fi

        # 只打印去掉签名参数的开头，避免整串 token 进日志
        echo "  → 成功抓到直播源：${STREAM_URL%%\?*}"
        echo "开始录制..."

        record_ffmpeg "$USERNAME" "$RECORD_PREFIX" "$LOG_DIR" "$STREAM_URL" || true

        echo "录制中断，等待 $RECORD_BREAK_SECONDS 秒后重新抓取源..."
        sleep "$RECORD_BREAK_SECONDS"
    done
}
