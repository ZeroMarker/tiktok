//! 引擎集成测试：用本地 HTTP 服务的 ffmpeg 生成流，验证
//! 分段输出、优雅停止、目录自愈与状态机。

use std::io::{Read, Write};
use std::net::TcpListener;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use dlr_core::engine::{Detector, Engine, EngineConfig, Phase};
use dlr_core::Platform;

fn ffmpeg_available() -> bool {
    std::process::Command::new("ffmpeg")
        .arg("-version")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .map(|s| s.success())
        .unwrap_or(false)
}

/// 固定返回一条流 URL 的探测器（跳过真实平台的检测逻辑）。
struct StaticDetector {
    url: String,
    nick: Option<String>,
}

impl Detector for StaticDetector {
    fn detect_stream_url(&mut self) -> Option<String> {
        Some(self.url.clone())
    }
    fn nickname(&mut self) -> Option<String> {
        self.nick.clone()
    }
}

/// 用 lavfi 生成 6 秒测试视频（无音频轨，验证 -map 0:a:0? 容错）。
fn make_test_clip(dir: &std::path::Path) -> PathBuf {
    let out = dir.join("test.mp4");
    let status = std::process::Command::new("ffmpeg")
        .args(["-y", "-f", "lavfi", "-i", "testsrc=size=160x120:rate=10", "-t", "6"])
        .args(["-pix_fmt", "yuv420p", out.to_str().unwrap()])
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .status()
        .unwrap();
    assert!(status.success(), "ffmpeg 生成测试片段失败");
    out
}

/// 极简静态 HTTP 服务：把整个文件作为一次响应体返回。
/// 引擎的 ffmpeg 命令带 `-headers`（http 输入选项），本地文件输入会报
/// "Option headers not found"，因此测试必须走 HTTP 路径（与生产一致）。
fn serve_clip(path: PathBuf) -> (String, std::thread::JoinHandle<()>) {
    let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
    let port = listener.local_addr().unwrap().port();
    let url = format!("http://127.0.0.1:{port}/test.mp4");
    let thread = std::thread::spawn(move || {
        for stream in listener.incoming() {
            let Ok(mut stream) = stream else { continue };
            // 读到请求头即可（ffmpeg 可能发 HEAD 或 GET，一律响应文件）
            let mut buf = [0u8; 2048];
            let _ = stream.read(&mut buf);
            let Ok(data) = std::fs::read(&path) else { continue };
            let head = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: video/mp4\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                data.len()
            );
            let mut resp = head.into_bytes();
            resp.extend_from_slice(&data);
            let _ = stream.write_all(&resp);
            let _ = stream.flush();
        }
    });
    (url, thread)
}

fn temp_root(tag: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("dlr-test-{tag}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

#[test]
fn segments_written_and_graceful_stop() {
    if !ffmpeg_available() {
        eprintln!("skip: ffmpeg 不可用");
        return;
    }
    let root = temp_root("segments");
    let clip = make_test_clip(&root);
    let (url, _server) = serve_clip(clip.clone());

    let mut cfg = EngineConfig::new(Platform::Youtube, "testchannel", root.join("recordings"));
    cfg.segment_seconds = 2;
    cfg.detect_interval = 1;
    cfg.break_seconds = 1;
    cfg.dir_watch_interval = 1;

    let engine = Engine::new(
        cfg,
        Box::new(StaticDetector { url: url.clone(), nick: Some("测试主播".into()) }),
    );
    let handle = engine.clone();
    let thread = std::thread::spawn(move || handle.run());

    // 等引擎进入录制并写出至少 1 个分段
    let deadline = Instant::now() + Duration::from_secs(20);
    let out_dir = loop {
        assert!(Instant::now() < deadline, "超时：未等到分段输出");
        let st = engine.status();
        if let Some(dir) = st.out_dir {
            let segments: Vec<_> = std::fs::read_dir(&dir)
                .map(|rd| {
                    rd.filter_map(|e| e.ok())
                        .filter(|e| e.path().extension().map(|x| x == "mp4").unwrap_or(false))
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            if !segments.is_empty() {
                break dir;
            }
        }
        std::thread::sleep(Duration::from_millis(200));
    };

    // 验证布局：平台_标识_昵称
    assert!(
        out_dir.file_name().unwrap().to_string_lossy().contains("youtube_testchannel"),
        "输出目录命名不符：{}",
        out_dir.display()
    );
    assert!(out_dir.file_name().unwrap().to_string_lossy().contains("测试主播"));

    // 验证录制期间停止：SIGTERM 优雅停止 ffmpeg
    engine.request_stop();
    let deadline = Instant::now() + Duration::from_secs(15);
    assert!(thread.join().is_ok(), "引擎线程未正常退出");
    assert!(Instant::now() < deadline, "引擎退出超时");
    assert_eq!(engine.status().phase_text, Phase::Stopped.as_str());

    // 至少产出一个 mp4 分段
    let segments: Vec<_> = std::fs::read_dir(&out_dir)
        .unwrap()
        .filter_map(|e| e.ok())
        .filter(|e| e.path().extension().map(|x| x == "mp4").unwrap_or(false))
        .collect();
    assert!(!segments.is_empty(), "未产出任何分段");
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn dir_self_heal_restores_deleted_output_dir() {
    if !ffmpeg_available() {
        eprintln!("skip: ffmpeg 不可用");
        return;
    }
    let root = temp_root("selfheal");
    let clip = make_test_clip(&root);
    let (url, _server) = serve_clip(clip.clone());

    let mut cfg = EngineConfig::new(Platform::Kick, "heal", root.join("recordings"));
    cfg.segment_seconds = 2;
    cfg.detect_interval = 1;
    cfg.break_seconds = 1;
    cfg.dir_watch_interval = 1;

    let engine = Engine::new(cfg, Box::new(StaticDetector { url: url.clone(), nick: None }));
    let handle = engine.clone();
    let thread = std::thread::spawn(move || handle.run());

    // 等到输出目录出现
    let deadline = Instant::now() + Duration::from_secs(20);
    let out_dir = loop {
        assert!(Instant::now() < deadline, "超时：输出目录未出现");
        if let Some(dir) = engine.status().out_dir {
            if dir.is_dir() {
                break dir;
            }
        }
        std::thread::sleep(Duration::from_millis(200));
    };

    // 删除整个输出目录（模拟外部清理），守护线程应在下个分段前重建
    std::fs::remove_dir_all(&out_dir).unwrap();
    let deadline = Instant::now() + Duration::from_secs(15);
    while !out_dir.is_dir() {
        assert!(Instant::now() < deadline, "超时：输出目录未自动重建");
        std::thread::sleep(Duration::from_millis(200));
    }

    engine.request_stop();
    let _ = thread.join();
    let _ = std::fs::remove_dir_all(&root);
}

#[test]
fn retries_when_detection_fails_then_recovers() {
    if !ffmpeg_available() {
        eprintln!("skip: ffmpeg 不可用");
        return;
    }
    let root = temp_root("retry");
    let clip = make_test_clip(&root);
    let (url, _server) = serve_clip(clip.clone());
    let fail_first = Arc::new(AtomicBool::new(true));

    struct FlakyDetector {
        url: String,
        fail_first: Arc<AtomicBool>,
    }
    impl Detector for FlakyDetector {
        fn detect_stream_url(&mut self) -> Option<String> {
            if self.fail_first.swap(false, Ordering::SeqCst) {
                None // 第一次检测失败 → 触发等待重试
            } else {
                Some(self.url.clone())
            }
        }
    }

    let mut cfg = EngineConfig::new(Platform::Soop, "flaky", root.join("recordings"));
    cfg.segment_seconds = 2;
    cfg.detect_interval = 1;
    cfg.break_seconds = 1;
    cfg.dir_watch_interval = 1;

    let engine = Engine::new(
        cfg,
        Box::new(FlakyDetector { url: url.clone(), fail_first: fail_first.clone() }),
    );
    let handle = engine.clone();
    let thread = std::thread::spawn(move || handle.run());

    let deadline = Instant::now() + Duration::from_secs(20);
    loop {
        assert!(Instant::now() < deadline, "超时：失败重试后未能录制");
        let st = engine.status();
        if st.detect_attempts >= 2 {
            if let Some(dir) = st.out_dir {
                let has_segments = std::fs::read_dir(&dir)
                    .map(|rd| {
                        rd.filter_map(|e| e.ok())
                            .filter(|e| e.path().extension().map(|x| x == "mp4").unwrap_or(false))
                            .count()
                            > 0
                    })
                    .unwrap_or(false);
                if has_segments {
                    break;
                }
            }
        }
        std::thread::sleep(Duration::from_millis(200));
    }

    engine.request_stop();
    let _ = thread.join();
    let _ = std::fs::remove_dir_all(&root);
}
