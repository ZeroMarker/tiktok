//! yt-dlp 子进程封装：取流与取昵称（对照 Python adapters/base.py + ytdlp.py）。

use std::io::Read;
use std::path::Path;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

use crate::platform::Platform;

const CAPTURE_TIMEOUT: Duration = Duration::from_secs(60);

/// 执行命令并取 stdout 第一行；失败/超时/空输出返回 None。
pub fn run_capture(cmd: &mut Command, timeout: Duration) -> Option<String> {
    let mut child = cmd
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .ok()?;

    let deadline = Instant::now() + timeout;
    let status = loop {
        match child.try_wait() {
            Ok(Some(status)) => break status,
            Ok(None) => {
                if Instant::now() >= deadline {
                    let _ = child.kill();
                    let _ = child.wait();
                    return None;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            Err(_) => {
                let _ = child.kill();
                return None;
            }
        }
    };
    if !status.success() {
        return None;
    }
    let mut out = String::new();
    child.stdout.take()?.read_to_string(&mut out).ok()?;
    out.lines().next().map(str::trim).filter(|s| !s.is_empty()).map(str::to_string)
}

/// yt-dlp 的 Cookie 参数（Netscape 文件优先，其次原始请求头）。
pub fn cookie_args(cookies: Option<&Path>, cookie_header: Option<&str>) -> Vec<String> {
    let mut args = Vec::new();
    if let Some(path) = cookies {
        args.push("--cookies".to_string());
        args.push(path.display().to_string());
    } else if let Some(header) = cookie_header {
        args.push("--cookie".to_string());
        args.push(header.to_string());
    }
    args
}

/// 通用平台取流：按格式优先级依次试，最后 impersonate 兜底。
///
/// 对照 Python `YTDLPAdapter.detect_stream_url`。
pub fn detect_via_ytdlp(
    platform: Platform,
    live_url: &str,
    cookies: Option<&Path>,
    cookie_header: Option<&str>,
) -> Option<String> {
    let cookie = if platform.passes_cookies_to_ytdlp() {
        cookie_args(cookies, cookie_header)
    } else {
        Vec::new()
    };
    for fmt in platform.formats() {
        let url = run_capture(
            Command::new("yt-dlp")
                .args(["--no-warnings", "-f", fmt])
                .args(&cookie)
                .args(["--get-url", live_url]),
            CAPTURE_TIMEOUT,
        );
        if url.is_some() {
            return url;
        }
    }
    // 兜底：impersonate 一次
    run_capture(
        Command::new("yt-dlp")
            .args(["--no-warnings", "-f", "b[ext=flv]/best"])
            .args(["--impersonate", "chrome"])
            .args(&cookie)
            .args(["--get-url", live_url]),
        CAPTURE_TIMEOUT,
    )
}

/// 通用平台昵称：channel 字段优先，其次 uploader。
///
/// 对照 Python `YTDLPAdapter.get_nickname`。
pub fn nickname_via_ytdlp(live_url: &str) -> Option<String> {
    for field in ["channel", "uploader"] {
        let value = run_capture(
            Command::new("yt-dlp").args([
                "--flat-playlist",
                "--no-warnings",
                "--skip-download",
                "--print",
                &format!("%({field})s"),
                live_url,
            ]),
            CAPTURE_TIMEOUT,
        );
        if let Some(v) = value {
            if v != "NA" {
                return Some(v);
            }
        }
    }
    None
}
