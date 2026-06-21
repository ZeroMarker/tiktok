# 使用方法：
#   . .\record.ps1
#   Record-TikTok -Username <tiktok_username>
# 示例： Record-TikTok -Username kobiritukii

function Format-PathPart {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    return (($Value -replace '[\/\\:*?"<>|]', '_').Trim())
}

function Record-TikTok {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$Username
    )

    $ErrorActionPreference = "Stop"

    $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    Push-Location $scriptDir

    try {
        $logDir = Join-Path "." "logs"

        Write-Host "正在获取 TikTok @$Username 的昵称..."
        $nickname = (& yt-dlp --no-warnings --skip-download --print "%(uploader)s" "https://www.tiktok.com/@$Username" 2>$null | Select-Object -First 1)

        if (-not [string]::IsNullOrWhiteSpace($nickname) -and $nickname -ne "NA") {
            $safeNickname = Format-PathPart $nickname
            $outputDir = Join-Path "." "${Username}+$safeNickname"
        } else {
            Write-Host "未获取到昵称，输出目录将只使用 username。"
            $outputDir = Join-Path "." $Username
        }

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
    } finally {
        Pop-Location
    }
}

# 如果直接运行脚本（非 dot-source），则执行函数
if ($MyInvocation.InvocationName -ne '.') {
    if (-not $Username) {
        Write-Host "用法：.\record.ps1 <TikTok 用户名>"
        Write-Host "示例：.\record.ps1 kobiritukii"
        exit 1
    }
    Record-TikTok -Username $Username
}