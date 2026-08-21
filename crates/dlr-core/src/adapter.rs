//! 平台适配器：把各平台的检测/昵称差异收敛到 [`Detector`] trait。
//! CLI 与桌面端共用。

use std::path::PathBuf;

use crate::engine::Detector;
use crate::platform::Platform;
use crate::util::extract_last_segment;
use crate::ytdlp::{cookie_args, run_capture};
use crate::{tiktok, ytdlp};

pub struct PlatformAdapter {
    platform: Platform,
    target: String,
    identifier: String,
    cookies: Option<PathBuf>,
    cookie_header: Option<String>,
}

impl PlatformAdapter {
    pub fn new(
        platform: Platform,
        target: impl Into<String>,
        cookies: Option<PathBuf>,
        cookie_header: Option<String>,
    ) -> Self {
        let target = target.into();
        Self {
            identifier: extract_last_segment(&target),
            platform,
            target,
            cookies,
            cookie_header,
        }
    }
}

impl Detector for PlatformAdapter {
    fn detect_stream_url(&mut self) -> Option<String> {
        match self.platform {
            Platform::Tiktok => {
                // 方法1/2/3：yt-dlp 变体（www/mobile × 是否 impersonate），带 Cookie。
                // 对照 Python TikTokAdapter.detect_stream_url。
                let cookie = cookie_args(self.cookies.as_deref(), self.cookie_header.as_deref());
                for host in ["www.tiktok.com", "m.tiktok.com"] {
                    let url = format!("https://{host}/@{}/live", self.identifier);
                    for extra in [
                        Vec::<String>::new(),
                        vec!["--impersonate".into(), "chrome".into()],
                    ] {
                        let stream = run_capture(
                            std::process::Command::new("yt-dlp")
                                .args(["--no-warnings", "-f", "b[ext=flv]/best"])
                                .args(&extra)
                                .args(&cookie)
                                .args(["--get-url", &url]),
                            std::time::Duration::from_secs(60),
                        );
                        if stream.is_some() {
                            return stream;
                        }
                    }
                }
                // 方法4：页面 + webcast API 兜底
                tiktok::get_stream_url(&self.identifier, self.cookies.as_deref())
            }
            _ => {
                let live_url = self.platform.live_url(&self.target);
                ytdlp::detect_via_ytdlp(
                    self.platform,
                    &live_url,
                    self.cookies.as_deref(),
                    self.cookie_header.as_deref(),
                )
            }
        }
    }

    fn nickname(&mut self) -> Option<String> {
        match self.platform {
            Platform::Tiktok => {
                // 页面解析优先（更稳定）；失败再用 yt-dlp %(channel)s 兜底。
                let nick = tiktok::get_nickname(&self.identifier, self.cookies.as_deref(), 3);
                if nick.is_some() {
                    return nick;
                }
                let profile = format!("https://www.tiktok.com/@{}", self.identifier);
                let cookie = cookie_args(self.cookies.as_deref(), self.cookie_header.as_deref());
                let value = run_capture(
                    std::process::Command::new("yt-dlp")
                        .args(["--flat-playlist", "--no-warnings", "--skip-download"])
                        .args(["--impersonate", "chrome"])
                        .args(["--print", "%(channel)s"])
                        .args(&cookie)
                        .arg(&profile),
                    std::time::Duration::from_secs(60),
                );
                value.filter(|v| v != "NA")
            }
            _ => {
                let live_url = self.platform.live_url(&self.target);
                ytdlp::nickname_via_ytdlp(&live_url)
            }
        }
    }
}
