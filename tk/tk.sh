#!/bin/bash
#
# tk.sh — TikTok 直播录制脚本
# 基于原始 record.sh (@ ~/tiktok/tk/record.sh, git: 0016772) 改进
#
# === 与原始 record.sh 的差异 ===
# - FLV 流格式: yt-dlp -f "b[ext=flv]" 强制 FLV，解决 HLS token 短导致仅录 12s 的问题
# - 断包防护: -fflags +discardcorrupt，防止 FLV 数据包损坏导致 ffmpeg 退出
# - 字幕过滤: -map 0:v -map 0:a，跳过 TikTok FLV 流的字幕流（MP4 不支持）
# - live_start_index: -live_start_index -1，加快 FLV 直播拉起速度
# - 时间戳: -reset_timestamps 1（无 -copyts），每个分段从 0:00 开始
# - 自动重试: while true 循环，断流后自动重试（原始脚本需手动重跑）
# - 昵称目录: 先用 yt-dlp 获取主播昵称，目录命名 user_nickname
# - 连续运行: 无 timeout，ffmpeg 持续运行，segment 干净切割（原始无 timeout）
# - 日志: 按日期写入 ./logs/ffmpeg_record_<user>_<date>.log
#
# 使用方法：
#   source ~/scripts/tk.sh
#   tk <tiktok_username>
# 示例： tk kobiritukii

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

tk() {
    if [ $# -ne 1 ]; then
        echo "用法：tk <TikTok 用户名>"
        echo "示例：tk kobiritukii"
        return 1
    fi

    local USERNAME="$1"
    local LOG_DIR="./logs"

    echo "正在获取 TikTok @${USERNAME} 的昵称..."
    local NICKNAME=$(get_nickname "https://www.tiktok.com/@${USERNAME}")

    local RECORD_PREFIX
    local OUTPUT_DIR

    if [ -n "$NICKNAME" ] && [ "$NICKNAME" != "NA" ]; then
        local SAFE_NICKNAME=$(sanitize_path_part "$NICKNAME")
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
    echo "每 10 分钟生成一个 MP4 文件"
    echo "输出目录：$(pwd)"
    echo "按 Ctrl+C 停止，或用 kill 杀掉进程"

    while true; do
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 尝试抓取直播源 @${USERNAME} ..."

        local STREAM_URL=$(yt-dlp "https://www.tiktok.com/@${USERNAME}/live" -f "b[ext=flv]" --get-url 2>/dev/null | head -n1)

        if [ -z "$STREAM_URL" ]; then
            echo "  → 直播未开启 / 抓取失败，等待 60 秒后重试..."
            sleep 60
            continue
        fi

        echo "  → 成功抓到源：${STREAM_URL}..."
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

        echo "录制中断，等待 10 秒后重新抓取源..."
        sleep 10
    done
}

# 如果直接运行脚本（非 source），则执行函数
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [ $# -ne 1 ]; then
        echo "用法：$0 <TikTok 用户名>"
        echo "示例：$0 kobiritukii"
        exit 1
    fi
    tk "$1"
fi
