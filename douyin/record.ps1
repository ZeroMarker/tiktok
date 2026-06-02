param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Identifier
)

# 使用方法：
#   .\record.ps1 <web_rid|抖音号|完整URL>
# 示例： .\record.ps1 1930162853
# 示例： .\record.ps1 @zhangsan
# 示例： .\record.ps1 https://live.douyin.com/1234567890

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

$logDir = Join-Path $scriptDir "logs"
$pyGetStream = Join-Path $scriptDir "get_stream.py"

function Format-PathPart {
    param([string]$Value)
    return (($Value -replace '[\/\\:*?"<>|]', '_').Trim())
}

$cleanInput = $Identifier -replace '^@', ''

# Get nickname
Write-Host "正在获取昵称..."
try {
    $nickname = (& python $pyGetStream $Identifier --get-nickname 2>$null)
} catch {
    $nickname = $null
}

if (-not [string]::IsNullOrWhiteSpace($nickname)) {
    $safeNickname = Format-PathPart $nickname
    $recordPrefix = "${cleanInput}_$safeNickname"
    $outputDir = Join-Path "." $recordPrefix
    Write-Host "昵称：$nickname"
} else {
    Write-Host "未获取到昵称，输出目录将只使用输入标识。"
    $recordPrefix = $cleanInput
    $outputDir = Join-Path "." $cleanInput
}

New-Item -ItemType Directory -Force -Path $outputDir | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Set-Location $outputDir

Write-Host "开始无人值守录制抖音直播间 $cleanInput"
Write-Host "每 10 分钟生成一个 MP4 文件"
Write-Host "输出目录：$(Get-Location)"
Write-Host "按 Ctrl+C 停止，或关闭窗口/结束进程"

while ($true) {
    $now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$now] 尝试抓取直播源 $cleanInput ..."

    try {
        $streamUrl = (& python $pyGetStream $Identifier --get-url 2>$null)
    } catch {
        $streamUrl = $null
    }

    if ([string]::IsNullOrWhiteSpace($streamUrl)) {
        Write-Host "  -> 直播未开启 / 抓取失败，等待 60 秒后重试..."
        Start-Sleep -Seconds 60
        continue
    }

    Write-Host "  -> 成功抓到源，开始录制..."

    $date = Get-Date -Format "yyyyMMdd"
    $logFile = Join-Path $logDir "ffmpeg_record_${cleanInput}_$date.log"
    $headers = "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36`r`nReferer: https://www.douyin.com/`r`n"

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
        "${recordPrefix}_%Y%m%d_%H%M%S.mp4" `
        2>> $logFile

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ffmpeg 异常退出（源可能已断），即将重试..."
    }

    Write-Host "录制中断，等待 10 秒后重新抓取源..."
    Start-Sleep -Seconds 10
}
