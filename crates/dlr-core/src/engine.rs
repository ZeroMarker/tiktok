//! 统一录制引擎：输出布局、检测循环、ffmpeg 分段与优雅停止。
//!
//! 对照 Python `scripts/dlr/engine.py`。平台差异收敛在 [`Detector`] 里。

use std::fs::{File, OpenOptions};
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use parking_lot::Mutex;

use crate::platform::Platform;
use crate::util::sanitize_path_part;

pub const FFMPEG_UA: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 \
(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36";

const LOG_CAP: usize = 4000;
const POLL_STEP: Duration = Duration::from_millis(100);

/// 直播源探测接口：CLI 用平台适配器，测试/桌面端可注入其他实现。
pub trait Detector: Send {
    /// 返回一条可用流 URL；未开播或抓取失败返回 None。
    fn detect_stream_url(&mut self) -> Option<String>;
    /// 尽力获取主播昵称；失败返回 None（不影响录制）。
    fn nickname(&mut self) -> Option<String> {
        None
    }
}

#[derive(Clone, Debug)]
pub struct EngineConfig {
    pub platform: Platform,
    pub target: String,
    pub recordings_root: PathBuf,
    pub cookies: Option<PathBuf>,
    pub cookie_header: Option<String>,
    pub segment_seconds: u32,
    pub detect_interval: u64,
    pub break_seconds: u64,
    pub dir_watch_interval: u64,
}

impl EngineConfig {
    pub fn new(platform: Platform, target: impl Into<String>, recordings_root: PathBuf) -> Self {
        Self {
            platform,
            target: target.into(),
            recordings_root,
            cookies: None,
            cookie_header: None,
            segment_seconds: 600,
            detect_interval: 60,
            break_seconds: 10,
            dir_watch_interval: 3,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase {
    Idle,
    Detecting,
    Recording,
    Stopping,
    Stopped,
}

impl Phase {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Idle => "待命",
            Self::Detecting => "检测中",
            Self::Recording => "录制中",
            Self::Stopping => "停止中",
            Self::Stopped => "已停止",
        }
    }

    pub fn running(self) -> bool {
        matches!(self, Self::Detecting | Self::Recording)
    }
}

/// 引擎状态快照（CLI/桌面端读取用）。
#[derive(Clone, Debug, Default)]
pub struct Status {
    pub identifier: String,
    pub phase_text: String,
    pub running: bool,
    pub nickname: Option<String>,
    pub out_dir: Option<PathBuf>,
    pub stream_hint: Option<String>,
    pub segments_written: u64,
    pub detect_attempts: u64,
    pub started_at: Option<String>,
    pub last_error: Option<String>,
}

/// 环形日志缓冲：引擎写入，桌面端增量读取。
#[derive(Debug)]
pub struct LogBuf {
    lines: std::collections::VecDeque<String>,
    seq: u64,
}

impl Default for LogBuf {
    fn default() -> Self {
        Self { lines: std::collections::VecDeque::new(), seq: 0 }
    }
}

impl LogBuf {
    pub fn push(&mut self, line: String) {
        if self.lines.len() >= LOG_CAP {
            self.lines.pop_front();
        }
        self.lines.push_back(line);
        self.seq += 1;
    }

    /// 返回 (当前 seq, 自 from_seq 之后的新行)。
    pub fn since(&self, from_seq: u64) -> (u64, Vec<String>) {
        let buffered = self.lines.len() as u64;
        let start = self.seq.saturating_sub(buffered);
        let skip = from_seq.saturating_sub(start) as usize;
        let new: Vec<String> = self.lines.iter().skip(skip).cloned().collect();
        (self.seq, new)
    }

    pub fn tail(&self, n: usize) -> Vec<String> {
        self.lines.iter().rev().take(n).rev().cloned().collect()
    }

    pub fn len(&self) -> u64 {
        self.seq
    }
}

/// 每频道一个实例，负责完整录制生命周期。
pub struct Engine {
    cfg: EngineConfig,
    identifier: String,
    detector: Mutex<Box<dyn Detector>>,
    stop: AtomicBool,
    status: Mutex<Status>,
    logs: Arc<Mutex<LogBuf>>,
    /// 正在运行的 ffmpeg 子进程 pid（0 = 无），供 stop 发 SIGTERM。
    ffmpeg_pid: AtomicU32,
}

impl Engine {
    pub fn new(cfg: EngineConfig, detector: Box<dyn Detector>) -> Arc<Self> {
        let identifier = crate::util::extract_last_segment(&cfg.target);
        Arc::new(Self {
            identifier: identifier.clone(),
            cfg,
            detector: Mutex::new(detector),
            stop: AtomicBool::new(false),
            status: Mutex::new(Status {
                identifier,
                phase_text: Phase::Idle.as_str().into(),
                ..Status::default()
            }),
            logs: Arc::new(Mutex::new(LogBuf::default())),
            ffmpeg_pid: AtomicU32::new(0),
        })
    }

    pub fn status(&self) -> Status {
        self.status.lock().clone()
    }

    pub fn logs(&self) -> Arc<Mutex<LogBuf>> {
        self.logs.clone()
    }

    pub fn identifier(&self) -> &str {
        &self.identifier
    }

    pub fn platform(&self) -> Platform {
        self.cfg.platform
    }

    pub fn target(&self) -> &str {
        &self.cfg.target
    }

    /// 优雅停止：置标志位 + 给正在运行的 ffmpeg 发 SIGTERM。
    pub fn request_stop(&self) {
        self.stop.store(true, Ordering::SeqCst);
        let pid = self.ffmpeg_pid.load(Ordering::SeqCst);
        if pid != 0 {
            terminate_pid(pid);
        }
        self.set_phase(Phase::Stopping);
    }

    pub fn is_stopping(&self) -> bool {
        self.stop.load(Ordering::SeqCst)
    }

    // ---- 日志与状态 ----

    fn log(&self, line: impl Into<String>) {
        let line = line.into();
        println!("{line}");
        println_flush();
        self.logs.lock().push(line);
    }

    fn log_err(&self, line: impl Into<String>) {
        let line = line.into();
        eprintln!("{line}");
        self.logs.lock().push(line);
    }

    fn set_phase(&self, phase: Phase) {
        let mut st = self.status.lock();
        st.phase_text = phase.as_str().into();
        st.running = phase.running();
    }

    // ---- 输出布局 ----

    /// 输出目录/文件名的公共前缀片段：平台_频道标识[_昵称]。
    fn name_parts(&self, nickname: Option<&str>) -> Vec<String> {
        let mut parts = vec![format!("{}_{}", self.cfg.platform, self.identifier)];
        if let Some(nick) = nickname {
            let safe = sanitize_path_part(nick);
            if !safe.is_empty() && safe != self.identifier {
                parts.push(safe);
            }
        }
        parts
    }

    pub fn output_dir(&self, nickname: Option<&str>) -> PathBuf {
        self.cfg.recordings_root.join(self.name_parts(nickname).join("_"))
    }

    /// 确保目录存在（含父目录）。目录可能被外部清理（如删除/手动删空目录）。
    fn ensure_dir(path: &Path) -> io::Result<()> {
        if !path.is_dir() {
            std::fs::create_dir_all(path)?;
        }
        Ok(())
    }

    // ---- 生命周期 ----

    pub fn run(&self) -> i32 {
        self.log(format!(
            "开始无人值守录制 {}：{}",
            self.cfg.platform, self.identifier
        ));
        self.set_phase(Phase::Detecting);
        {
            let mut st = self.status.lock();
            st.started_at = Some(chrono::Local::now().format("%Y-%m-%d %H:%M:%S").to_string());
        }

        let mut nickname = self.safe_nickname();
        match &nickname {
            Some(n) => self.log(format!("主播昵称：{n}")),
            None => self.log("未获取到昵称，输出目录将只使用频道标识（后续会尝试补获取）。"),
        }
        {
            self.status.lock().nickname = nickname.clone();
        }

        let mut out_dir = self.output_dir(nickname.as_deref());
        let _ = Self::ensure_dir(&out_dir);
        let log_dir = self.cfg.recordings_root.join("logs");
        let _ = Self::ensure_dir(&log_dir);
        self.status.lock().out_dir = Some(out_dir.clone());

        self.log(format!("每 {} 秒生成一个分段", self.cfg.segment_seconds));
        self.log(format!("输出目录：{}", out_dir.display()));

        while !self.is_stopping() {
            // 未开播轮询期间补获取昵称（仅当首次失败时才有动作）
            if nickname.is_none() {
                nickname = self.safe_nickname();
                if let Some(n) = &nickname {
                    let new_dir = self.output_dir(Some(n));
                    let _ = Self::ensure_dir(&new_dir);
                    out_dir = new_dir;
                    {
                        let mut st = self.status.lock();
                        st.nickname = nickname.clone();
                        st.out_dir = Some(out_dir.clone());
                    }
                    self.log(format!(
                        "补获取到主播昵称：{n}，新输出目录：{}",
                        out_dir.display()
                    ));
                }
            }

            self.log(format!(
                "[{}] 尝试抓取直播源 @{} ...",
                chrono::Local::now().format("%Y-%m-%d %H:%M:%S"),
                self.identifier
            ));
            self.set_phase(Phase::Detecting);
            self.status.lock().detect_attempts += 1;

            let stream_url = self.detector.lock().detect_stream_url();
            let Some(stream_url) = stream_url else {
                self.log(format!(
                    "  → 直播未开启 / 抓取失败，等待 {} 秒后重试...",
                    self.cfg.detect_interval
                ));
                self.sleep_interruptible(self.cfg.detect_interval);
                continue;
            };

            // 只记录去掉签名参数的开头，避免整串 token 进日志
            let hint = stream_url.split('?').next().unwrap_or(&stream_url).to_string();
            self.log(format!("  → 成功抓到直播源：{hint}"));
            self.log("开始录制...");
            {
                let mut st = self.status.lock();
                st.stream_hint = Some(hint);
            }
            self.set_phase(Phase::Recording);

            self.record(&out_dir, &log_dir, &stream_url, nickname.as_deref());
            self.refresh_segment_count(&out_dir);

            self.set_phase(Phase::Detecting);
            self.status.lock().stream_hint = None;
            self.log(format!(
                "录制中断，等待 {} 秒后重新抓取源...",
                self.cfg.break_seconds
            ));
            if !self.is_stopping() {
                self.sleep_interruptible(self.cfg.break_seconds);
            }
        }

        self.set_phase(Phase::Stopped);
        self.log("录制已停止。");
        0
    }

    fn safe_nickname(&self) -> Option<String> {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            self.detector.lock().nickname()
        }))
        .unwrap_or_else(|_| {
            self.log_err("获取昵称失败（detector panic）");
            None
        })
    }

    /// 可中断睡眠：返回是否因停止信号提前结束。
    fn sleep_interruptible(&self, secs: u64) -> bool {
        let deadline = Instant::now() + Duration::from_secs(secs);
        while Instant::now() < deadline {
            if self.is_stopping() {
                return true;
            }
            std::thread::sleep(POLL_STEP.min(deadline.saturating_duration_since(Instant::now())));
        }
        self.is_stopping()
    }

    // ---- 录制回合 ----

    fn record(&self, out_dir: &Path, log_dir: &Path, stream_url: &str, nickname: Option<&str>) {
        let prefix = self.name_parts(nickname).join("_");
        let date = chrono::Local::now().format("%Y%m%d").to_string();
        let log_file = log_dir.join(format!("ffmpeg_record_{prefix}_{date}.log"));
        let output_pattern = out_dir.join(format!("{prefix}_%Y%m%d_%H%M%S.mp4"));

        // 健壮性：目录可能在循环等待期间被外部删除，启动前再次确保存在；
        // 任一目录创建失败则放弃本回合，由外层循环重试，不中断监控。
        if let Err(exc) = Self::ensure_dir(out_dir).and_then(|_| Self::ensure_dir(log_dir)) {
            self.log_err(format!("创建输出/日志目录失败，本轮回合放弃：{exc}"));
            return;
        }

        let mut cmd = Command::new("ffmpeg");
        cmd.arg("-nostdin")
            .args(["-fflags", "+discardcorrupt"])
            .arg("-headers")
            .arg(format!(
                "User-Agent: {FFMPEG_UA}\r\nReferer: {}\r\n",
                self.cfg.platform.referer()
            ))
            .args(["-reconnect", "1"])
            .args(["-reconnect_streamed", "1"])
            .args(["-reconnect_delay_max", "30"])
            .args(["-rw_timeout", "30000000"])
            .arg("-i")
            .arg(stream_url)
            .args(["-c", "copy"]);
        if self.cfg.platform.bsf_aac() {
            cmd.args(["-bsf:a", "aac_adtstoasc"]);
        }
        cmd.args(["-map", "0:v:0"])
            .args(["-map", "0:a:0?"])
            .args(["-f", "segment"])
            .args(["-segment_time", &self.cfg.segment_seconds.to_string()])
            .args(["-segment_format", "mp4"])
            .args(["-reset_timestamps", "1"])
            .args(["-strftime", "1"])
            .arg(&output_pattern);

        // 录制全程由守护线程盯着输出目录：中途被删也能在下个分段前重建。
        let watcher_stop = Arc::new(AtomicBool::new(false));
        let watcher = {
            let out_dir = out_dir.to_path_buf();
            let interval = Duration::from_secs(self.cfg.dir_watch_interval.max(1));
            let stop = watcher_stop.clone();
            let logs = self.logs.clone();
            std::thread::Builder::new()
                .name(format!("dirwatch-{}", self.identifier))
                .spawn(move || {
                    // 200ms 粒度检查停止标志，避免 join 阻塞一整个 interval。
                    let mut waited = Duration::ZERO;
                    while !stop.load(Ordering::SeqCst) {
                        std::thread::sleep(Duration::from_millis(200));
                        if stop.load(Ordering::SeqCst) {
                            break;
                        }
                        waited += Duration::from_millis(200);
                        if waited < interval {
                            continue;
                        }
                        waited = Duration::ZERO;
                        if !out_dir.is_dir() {
                            match std::fs::create_dir_all(&out_dir) {
                                Ok(()) => logs.lock().push(format!(
                                    "检测到输出目录被删除，已自动重建：{}",
                                    out_dir.display()
                                )),
                                Err(exc) => logs.lock().push(format!(
                                    "重建输出目录失败：{exc}"
                                )),
                            }
                        }
                    }
                })
                .ok()
        };

        let rc = self.run_ffmpeg(&mut cmd, &log_file);

        watcher_stop.store(true, Ordering::SeqCst);
        if let Some(h) = watcher {
            let _ = h.join();
        }
        self.ffmpeg_pid.store(0, Ordering::SeqCst);

        if rc != 0 && !self.is_stopping() {
            self.log(format!("ffmpeg 异常退出（rc={rc}，源可能已断），即将重试..."));
        }
    }

    /// 统计输出目录中已落盘的 MP4 分段数并写入状态。
    fn refresh_segment_count(&self, out_dir: &Path) {
        let count = std::fs::read_dir(out_dir)
            .map(|rd| {
                rd.filter_map(|e| e.ok())
                    .filter(|e| e.path().extension().map(|x| x == "mp4").unwrap_or(false))
                    .count()
            })
            .unwrap_or(0);
        self.status.lock().segments_written = count as u64;
    }

    /// 启动 ffmpeg 并等待结束；收到停止信号时先 SIGTERM 后 SIGKILL。
    fn run_ffmpeg(&self, cmd: &mut Command, log_file: &Path) -> i32 {
        let mut spawn = || -> io::Result<Child> {
            let log_fh: File = OpenOptions::new().create(true).append(true).open(log_file)?;
            let log_err = log_fh.try_clone()?;
            cmd.stdin(Stdio::null())
                .stdout(Stdio::from(log_fh))
                .stderr(Stdio::from(log_err));
            cmd.spawn()
        };

        let mut child = match spawn() {
            Ok(c) => c,
            Err(exc) => {
                self.log_err(format!("录制回合启动失败：{exc}，即将重试..."));
                return -1;
            }
        };
        self.ffmpeg_pid.store(child.id(), Ordering::SeqCst);

        let mut sent_term = false;
        let mut term_at: Option<Instant> = None;
        loop {
            match child.try_wait() {
                Ok(Some(status)) => return status.code().unwrap_or(-1),
                Ok(None) => {
                    if self.is_stopping() && !sent_term {
                        sent_term = true;
                        term_at = Some(Instant::now());
                        terminate_pid(child.id());
                    }
                    if let Some(at) = term_at {
                        if at.elapsed() > Duration::from_secs(10) {
                            let _ = child.kill();
                            let _ = child.wait();
                            return -1;
                        }
                    }
                    std::thread::sleep(POLL_STEP);
                }
                Err(exc) => {
                    self.log_err(format!("录制回合异常：{exc}，即将重试..."));
                    let _ = child.kill();
                    return -1;
                }
            }
        }
    }
}

#[cfg(unix)]
fn terminate_pid(pid: u32) {
    unsafe {
        libc::kill(pid as i32, libc::SIGTERM);
    }
}

#[cfg(not(unix))]
fn terminate_pid(_pid: u32) {}

fn println_flush() {
    use std::io::Write;
    let _ = io::stdout().flush();
}
