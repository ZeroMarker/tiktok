param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Username
)

# 使用方法：
#   .\record.ps1 <tiktok_username>
# 示例： .\record.ps1 kobiritukii

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$outputDir = Join-Path "." "tiktok_records_$Username" # 每个账号用独立文件夹，避免混在一起
$logDir = Join-Path "." "logs"

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $outputDir

Write-Host "开始无人值守录制 TikTok @$Username"
Write-Host "每 10 分钟生成一个 MP4 文件"
Write-Host "输出目录：$(Get-Location)"
Write-Host "按 Ctrl+C 停止，或关闭窗口/结束进程"

while ($true) {
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$now] 尝试抓取直播源 @$Username ..."

    # 抓取直播 m3u8 地址（只取第一行，避免多行干扰）
    $streamUrl = (& yt-dlp "https://www.tiktok.com/@$Username/live" --get-url 2>$null | Select-Object -First 1)

    if ([string]::IsNullOrWhiteSpace($streamUrl)) {
        Write-Host "  -> 直播未开启 / 抓取失败，等待 60 秒后重试..."
        Start-Sleep -Seconds 60
        continue
    }

    Write-Host "  -> 成功抓到源：$streamUrl..."
    Write-Host "开始录制..."

    $date = Get-Date -Format "yyyyMMdd"
    $logFile = Join-Path "..\logs" "ffmpeg_record_${Username}_$date.log"
    $headers = "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36`r`nReferer: https://www.tiktok.com/`r`n"

    & ffmpeg `
        -headers $headers `
        -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 30 -timeout 30000000 `
        -i $streamUrl `
        -c copy -bsf:a aac_adtstoasc `
        -map 0 -reset_timestamps 1 `
        -f segment `
        -segment_time 600 `
        -segment_format mp4 `
        -strftime 1 `
        "${Username}_%Y%m%d_%H%M%S.mp4" `
        2>> $logFile

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ffmpeg 异常退出（源可能已断），即将重试..."
    }

    Write-Host "录制中断，等待 10 秒后重新抓取源..."
    Start-Sleep -Seconds 10
}
