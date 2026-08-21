//! dlr — 多平台无人值守直播录制引擎 CLI（对照 Python scripts/dlr.py）。

use std::path::PathBuf;

use dlr_core::adapter::PlatformAdapter;
use dlr_core::engine::{Engine, EngineConfig};
use dlr_core::platform::Platform;

const USAGE: &str = "\
用法：dlr <platform> <target> [选项]

平台：
    youtube kick chzzk soop tiktok douyin

选项：
    --cookies FILE       Netscape 格式 Cookie 文件（抖音等需要登录的平台）
    --cookie HEADER      原始 Cookie 请求头
    --recordings-dir DIR 录制输出根目录（默认 $RECORDINGS_DIR 或 ./recordings）
    --segment-seconds N  每段 MP4 时长（默认 600）
    --detect-interval N  未开播时的重试间隔（默认 60）
    --break-seconds N    断流后重新抓取间隔（默认 10）";

fn parse_args() -> Result<EngineConfig, String> {
    let argv: Vec<String> = std::env::args().skip(1).collect();
    if argv.is_empty() || argv.iter().any(|a| a == "-h" || a == "--help") {
        println!("{USAGE}");
        std::process::exit(0);
    }
    if argv.len() < 2 {
        return Err("缺少 <platform> <target> 参数".into());
    }
    let platform = Platform::parse(&argv[0]).ok_or_else(|| {
        format!("不支持的平台：{}（支持：youtube kick chzzk soop tiktok douyin）", argv[0])
    })?;
    let target = argv[1].clone();

    let mut cookies: Option<PathBuf> = None;
    let mut cookie_header: Option<String> = None;
    let mut recordings_dir: Option<PathBuf> = None;
    let mut segment_seconds = 600u32;
    let mut detect_interval = 60u64;
    let mut break_seconds = 10u64;

    let mut i = 2;
    while i < argv.len() {
        let flag = argv[i].as_str();
        let take_value = |i: usize, flag: &str| -> Result<String, String> {
            argv.get(i + 1)
                .cloned()
                .ok_or_else(|| format!("选项 {flag} 缺少参数"))
        };
        match flag {
            "--cookies" => cookies = Some(PathBuf::from(take_value(i, flag)?)),
            "--cookie" => cookie_header = Some(take_value(i, flag)?),
            "--recordings-dir" => recordings_dir = Some(PathBuf::from(take_value(i, flag)?)),
            "--segment-seconds" => {
                segment_seconds = take_value(i, flag)?
                    .parse()
                    .map_err(|_| "segment-seconds 必须是整数".to_string())?
            }
            "--detect-interval" => {
                detect_interval = take_value(i, flag)?
                    .parse()
                    .map_err(|_| "detect-interval 必须是整数".to_string())?
            }
            "--break-seconds" => {
                break_seconds = take_value(i, flag)?
                    .parse()
                    .map_err(|_| "break-seconds 必须是整数".to_string())?
            }
            other => return Err(format!("未知选项：{other}")),
        }
        i += 2;
    }

    let root = recordings_dir
        .or_else(|| std::env::var("RECORDINGS_DIR").ok().map(PathBuf::from))
        .unwrap_or_else(|| PathBuf::from("./recordings"));
    let root = if root.is_absolute() {
        root
    } else {
        std::env::current_dir()
            .map(|c| c.join(&root))
            .unwrap_or(root)
    };

    let mut cfg = EngineConfig::new(platform, target, root);
    cfg.cookies = cookies;
    cfg.cookie_header = cookie_header;
    cfg.segment_seconds = segment_seconds;
    cfg.detect_interval = detect_interval;
    cfg.break_seconds = break_seconds;
    Ok(cfg)
}

fn main() {
    let cfg = match parse_args() {
        Ok(cfg) => cfg,
        Err(msg) => {
            eprintln!("错误：{msg}");
            eprintln!("{USAGE}");
            std::process::exit(2);
        }
    };

    let adapter = PlatformAdapter::new(cfg.platform, cfg.target.clone(), cfg.cookies.clone(), cfg.cookie_header.clone());
    let engine = Engine::new(cfg, Box::new(adapter));

    let handle = engine.clone();
    if let Err(e) = ctrlc::set_handler(move || {
        handle.request_stop();
    }) {
        eprintln!("设置信号处理器失败：{e}");
    }

    let rc = engine.run();
    std::process::exit(rc);
}
