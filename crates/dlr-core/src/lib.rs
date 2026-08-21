//! dlr-core — 多平台无人值守直播录制引擎（Rust 版）。
//!
//! 所有平台共用同一引擎（检测、输出布局、ffmpeg 分段、优雅停止、断流重试），
//! 平台差异收敛为适配器（见 [`platform::Platform`] 与 [`tiktok`]）。

pub mod adapter;
pub mod engine;
pub mod platform;
pub mod tiktok;
pub mod util;
pub mod ytdlp;

pub use adapter::PlatformAdapter;
pub use engine::{Engine, EngineConfig, LogBuf, Phase, Status};
pub use platform::Platform;
pub use util::{extract_last_segment, sanitize_path_part};
