//! 平台枚举与每平台配置（对照 Python 版 adapters/ytdlp.py 的 CONFIG）。

use std::fmt;

/// 支持的平台：与 Python `dlr.py` 的 choices 一致。
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Platform {
    Tiktok,
    Douyin,
    Youtube,
    Kick,
    Chzzk,
    Soop,
}

impl Platform {
    pub const ALL: [Platform; 6] = [
        Platform::Tiktok,
        Platform::Douyin,
        Platform::Youtube,
        Platform::Kick,
        Platform::Chzzk,
        Platform::Soop,
    ];

    pub fn parse(s: &str) -> Option<Self> {
        match s.to_ascii_lowercase().as_str() {
            "tiktok" => Some(Self::Tiktok),
            "douyin" => Some(Self::Douyin),
            "youtube" => Some(Self::Youtube),
            "kick" => Some(Self::Kick),
            "chzzk" => Some(Self::Chzzk),
            "soop" => Some(Self::Soop),
            _ => None,
        }
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Tiktok => "tiktok",
            Self::Douyin => "douyin",
            Self::Youtube => "youtube",
            Self::Kick => "kick",
            Self::Chzzk => "chzzk",
            Self::Soop => "soop",
        }
    }

    /// ffmpeg 请求头 Referer。
    pub fn referer(self) -> &'static str {
        match self {
            Self::Tiktok => "https://www.tiktok.com/",
            Self::Douyin => "https://www.douyin.com/",
            Self::Youtube => "https://www.youtube.com/",
            Self::Kick => "https://kick.com/",
            Self::Chzzk => "https://chzzk.naver.com/",
            Self::Soop => "https://play.sooplive.co.kr/",
        }
    }

    /// 是否给音频加 aac_adtstoasc 比特流过滤（FLV 源转 MP4 需要）。
    pub fn bsf_aac(self) -> bool {
        matches!(self, Self::Tiktok | Self::Douyin | Self::Soop)
    }

    /// yt-dlp 格式优先级。
    pub fn formats(self) -> &'static [&'static str] {
        match self {
            Self::Tiktok | Self::Douyin => &["b[ext=flv]/best"],
            Self::Youtube | Self::Kick | Self::Chzzk => &["best[ext=mp4]/best", "b[ext=flv]/best"],
            Self::Soop => &["best", "b[ext=flv]/best"],
        }
    }

    /// 直播页 URL（target 可能本身就是 URL）。
    pub fn live_url(self, target: &str) -> String {
        let is_url = target.starts_with("http://") || target.starts_with("https://");
        match self {
            Self::Tiktok => {
                let id = crate::util::extract_last_segment(target);
                format!("https://www.tiktok.com/@{id}/live")
            }
            Self::Douyin => {
                if is_url {
                    target.to_string()
                } else {
                    format!("https://live.douyin.com/{target}")
                }
            }
            Self::Youtube => {
                if is_url {
                    target.to_string()
                } else {
                    format!("https://www.youtube.com/@{target}/live")
                }
            }
            Self::Kick => format!("https://kick.com/{target}"),
            Self::Chzzk => format!("https://chzzk.naver.com/live/{target}"),
            Self::Soop => {
                if is_url {
                    target.to_string()
                } else {
                    format!("https://play.sooplive.co.kr/{target}")
                }
            }
        }
    }

    /// 是否给 yt-dlp 透传 Cookie（Python 版仅 tiktok / douyin 透传）。
    pub fn passes_cookies_to_ytdlp(self) -> bool {
        matches!(self, Self::Tiktok | Self::Douyin)
    }
}

impl fmt::Display for Platform {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_all_platforms() {
        for p in Platform::ALL {
            assert_eq!(Platform::parse(p.as_str()), Some(p));
        }
        assert_eq!(Platform::parse("nope"), None);
    }

    #[test]
    fn live_url_forms() {
        assert_eq!(
            Platform::Tiktok.live_url("https://www.tiktok.com/@foo/live"),
            "https://www.tiktok.com/@foo/live"
        );
        assert_eq!(
            Platform::Youtube.live_url("bar"),
            "https://www.youtube.com/@bar/live"
        );
        assert_eq!(Platform::Kick.live_url("baz"), "https://kick.com/baz");
        assert_eq!(
            Platform::Chzzk.live_url("abc"),
            "https://chzzk.naver.com/live/abc"
        );
        assert_eq!(
            Platform::Soop.live_url("https://play.sooplive.co.kr/x"),
            "https://play.sooplive.co.kr/x"
        );
        assert_eq!(
            Platform::Douyin.live_url("123456"),
            "https://live.douyin.com/123456"
        );
    }
}
