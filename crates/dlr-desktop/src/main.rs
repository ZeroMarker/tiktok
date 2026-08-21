//! dlr-desktop — 直播录制桌面端管理（egui）。
//!
//! 功能：任务管理（添加/停止/删除）、实时状态与日志、录制文件浏览/删除、
//! 参数设置（录制目录、分段时长、重试间隔、Cookie）。任务在本进程内
//! 线程运行引擎，不依赖 systemd，可直接在桌面机使用。

use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::thread::JoinHandle;
use std::time::{Duration, Instant, SystemTime};

use dlr_core::adapter::PlatformAdapter;
use dlr_core::engine::{Engine, EngineConfig};
use dlr_core::Platform;
use eframe::egui;
use serde::{Deserialize, Serialize};

const APP_TITLE: &str = "DLR 桌面端 — 多平台直播录制";

// ---------- 设置持久化 ----------

#[derive(Clone, Serialize, Deserialize)]
struct Settings {
    recordings_dir: String,
    segment_seconds: u32,
    detect_interval: u64,
    break_seconds: u64,
    cookies_path: String,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            recordings_dir: "./recordings".into(),
            segment_seconds: 600,
            detect_interval: 60,
            break_seconds: 10,
            cookies_path: String::new(),
        }
    }
}

fn config_path() -> PathBuf {
    let base = std::env::var_os("XDG_CONFIG_HOME")
        .map(PathBuf::from)
        .or_else(|| std::env::var_os("HOME").map(|h| PathBuf::from(h).join(".config")))
        .unwrap_or_else(|| PathBuf::from("."));
    base.join("dlr-desktop").join("config.json")
}

fn load_settings() -> Settings {
    std::fs::read_to_string(config_path())
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn save_settings(settings: &Settings) {
    if let Some(parent) = config_path().parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(json) = serde_json::to_string_pretty(settings) {
        let _ = std::fs::write(config_path(), json);
    }
}

// ---------- 任务 ----------

struct Task {
    platform: Platform,
    target: String,
    engine: Arc<Engine>,
    thread: Option<JoinHandle<()>>,
    last_log_seq: u64,
    lines: Vec<String>,
}

impl Task {
    fn start(&mut self) {
        if self.thread.is_some() {
            return;
        }
        let engine = self.engine.clone();
        self.thread = Some(std::thread::spawn(move || {
            let _ = engine.run();
        }));
    }

    fn stop(&self) {
        self.engine.request_stop();
    }

    fn drain_logs(&mut self) {
        let logs = self.engine.logs();
        let (seq, new) = logs.lock().since(self.last_log_seq);
        self.last_log_seq = seq;
        if self.lines.len() + new.len() > 2000 {
            let drop = self.lines.len() + new.len() - 2000;
            self.lines.drain(..drop);
        }
        self.lines.extend(new);
    }
}

// ---------- 录制文件 ----------

struct RecFile {
    rel: String,
    size: u64,
    modified: SystemTime,
}

fn scan_recordings(root: &Path, limit: usize) -> Vec<RecFile> {
    fn walk(dir: &Path, prefix: &str, out: &mut Vec<RecFile>, depth: u8) {
        if depth > 3 {
            return;
        }
        let Ok(entries) = std::fs::read_dir(dir) else { return };
        for entry in entries.flatten() {
            let path = entry.path();
            let name = entry.file_name().to_string_lossy().to_string();
            let rel = if prefix.is_empty() { name } else { format!("{prefix}/{name}") };
            if path.is_dir() {
                walk(&path, &rel, out, depth + 1);
            } else if is_video(&path) {
                if let Ok(meta) = std::fs::metadata(&path) {
                    out.push(RecFile { rel, size: meta.len(), modified: meta.modified().unwrap_or(SystemTime::UNIX_EPOCH) });
                }
            }
        }
    }
    let mut files = Vec::new();
    walk(root, "", &mut files, 0);
    files.sort_by(|a, b| b.modified.cmp(&a.modified));
    files.truncate(limit);
    files
}

fn is_video(path: &Path) -> bool {
    matches!(
        path.extension().and_then(|e| e.to_str()).map(|e| e.to_ascii_lowercase()).as_deref(),
        Some("mp4" | "mkv" | "ts" | "flv" | "mov")
    )
}

fn human_size(bytes: u64) -> String {
    const UNITS: [&str; 4] = ["B", "KB", "MB", "GB"];
    let mut v = bytes as f64;
    let mut unit = 0;
    while v >= 1024.0 && unit < UNITS.len() - 1 {
        v /= 1024.0;
        unit += 1;
    }
    if unit == 0 {
        format!("{bytes} B")
    } else {
        format!("{v:.1} {}", UNITS[unit])
    }
}

// ---------- 应用 ----------

#[derive(PartialEq, Clone, Copy)]
enum Tab {
    Tasks,
    Recordings,
}

struct DesktopApp {
    settings: Settings,
    settings_open: bool,
    tasks: Vec<Task>,
    selected: Option<usize>,
    new_platform: Platform,
    new_target: String,
    tab: Tab,
    recordings: Vec<RecFile>,
    rec_search: String,
    rec_loaded_at: Option<Instant>,
    rec_total_size: u64,
    confirm_delete: Option<usize>,
}

impl DesktopApp {
    fn new(_cc: &eframe::CreationContext<'_>) -> Self {
        install_cjk_font(&_cc.egui_ctx);
        Self {
            settings: load_settings(),
            settings_open: false,
            tasks: Vec::new(),
            selected: None,
            new_platform: Platform::Tiktok,
            new_target: String::new(),
            tab: Tab::Tasks,
            recordings: Vec::new(),
            rec_search: String::new(),
            rec_loaded_at: None,
            rec_total_size: 0,
            confirm_delete: None,
        }
    }

    fn add_task(&mut self, target: String) {
        let target = target.trim().to_string();
        if target.is_empty() {
            return;
        }
        let mut cfg = EngineConfig::new(
            self.new_platform,
            target.clone(),
            PathBuf::from(&self.settings.recordings_dir),
        );
        cfg.segment_seconds = self.settings.segment_seconds.max(1);
        cfg.detect_interval = self.settings.detect_interval.max(1);
        cfg.break_seconds = self.settings.break_seconds.max(1);
        if !self.settings.cookies_path.trim().is_empty() {
            cfg.cookies = Some(PathBuf::from(self.settings.cookies_path.trim()));
        }
        let adapter = PlatformAdapter::new(self.new_platform, target.clone(), cfg.cookies.clone(), None);
        let engine = Engine::new(cfg, Box::new(adapter));
        let mut task = Task {
            platform: self.new_platform,
            target,
            engine,
            thread: None,
            last_log_seq: 0,
            lines: Vec::new(),
        };
        task.start();
        self.tasks.push(task);
        self.selected = Some(self.tasks.len() - 1);
        self.new_target.clear();
    }

    fn remove_task(&mut self, idx: usize) {
        if let Some(task) = self.tasks.get(idx) {
            task.stop();
        }
        // 线程句柄 drop 即 detach：引擎会在停止标志后自行退出。
        self.tasks.remove(idx);
        if let Some(sel) = self.selected {
            if sel >= self.tasks.len() {
                self.selected = if self.tasks.is_empty() { None } else { Some(self.tasks.len() - 1) };
            }
        }
    }

    fn reload_recordings(&mut self) {
        let root = PathBuf::from(&self.settings.recordings_dir);
        self.recordings = scan_recordings(&root, 500);
        self.rec_total_size = self.recordings.iter().map(|f| f.size).sum();
        self.rec_loaded_at = Some(Instant::now());
    }

    // ---- UI ----

    fn ui_top(&mut self, ui: &mut egui::Ui) {
        egui::Panel::top("top").show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.heading(APP_TITLE);
                let running = self.tasks.iter().filter(|t| t.engine.status().running).count();
                ui.label(format!("运行中任务：{}/{}", running, self.tasks.len()));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.selectable_label(self.tab == Tab::Recordings, "录制文件")
                        .clicked()
                        .then(|| {
                            self.tab = Tab::Recordings;
                            self.reload_recordings();
                        });
                    ui.selectable_label(self.tab == Tab::Tasks, "任务")
                        .clicked()
                        .then(|| self.tab = Tab::Tasks);
                    if ui.button("设置").clicked() {
                        self.settings_open = true;
                    }
                });
            });
        });
    }

    fn ui_sidebar(&mut self, ui: &mut egui::Ui) {
        egui::Panel::left("tasks")
            .resizable(true)
            .default_size(300.0)
            .show(ui, |ui| {
                ui.add_space(4.0);
                ui.heading("任务");
                ui.separator();
                ui.horizontal(|ui| {
                    ui.label("平台");
                    egui::ComboBox::from_id_salt("platform")
                        .selected_text(self.new_platform.as_str())
                        .show_ui(ui, |ui| {
                            for p in Platform::ALL {
                                ui.selectable_value(&mut self.new_platform, p, p.as_str());
                            }
                        });
                });
                ui.horizontal(|ui| {
                    ui.label("目标");
                    ui.add(
                        egui::TextEdit::singleline(&mut self.new_target)
                            .hint_text("用户名 / 频道ID / 直播URL")
                            .desired_width(f32::INFINITY),
                    );
                });
                if ui.button("添加任务").clicked() {
                    self.add_task(self.new_target.clone());
                }
                ui.separator();

                let mut remove: Option<usize> = None;
                let mut stop: Option<usize> = None;
                for (i, task) in self.tasks.iter_mut().enumerate() {
                    let st = task.engine.status();
                    let running = st.running;
                    let label = format!("[{}] {} — {}", task.platform, st.identifier, st.phase_text);
                    if ui.selectable_label(self.selected == Some(i), label).clicked() {
                        self.selected = Some(i);
                    }
                    ui.horizontal(|ui| {
                        ui.add_space(16.0);
                        if running {
                            if ui.small_button("停止").clicked() {
                                stop = Some(i);
                            }
                        }
                        if ui.small_button("删除").clicked() {
                            remove = Some(i);
                        }
                    });
                }
                if let Some(i) = stop {
                    self.tasks[i].stop();
                }
                if let Some(i) = remove {
                    self.remove_task(i);
                }
                ui.with_layout(egui::Layout::bottom_up(egui::Align::Min), |ui| {
                    ui.label(format!("录制目录：{}", self.settings.recordings_dir));
                });
            });
    }

    fn ui_task_detail(&mut self, ui: &mut egui::Ui) {
        egui::CentralPanel::default().show(ui, |ui| {
            let Some(idx) = self.selected else {
                ui.centered_and_justified(|ui| ui.label("选择左侧任务查看状态与日志"));
                return;
            };
            let Some(task) = self.tasks.get_mut(idx) else { return };
            task.drain_logs();
            let st = task.engine.status();

            ui.heading(format!("[{}] {}", task.platform, task.target));
            ui.separator();
            egui::Grid::new("status")
                .num_columns(2)
                .spacing([12.0, 6.0])
                .show(ui, |ui| {
                    let phase_color = match st.phase_text.as_str() {
                        "录制中" => egui::Color32::from_rgb(0x2e, 0xcc, 0x71),
                        "检测中" => egui::Color32::from_rgb(0xf3, 0x9c, 0x12),
                        _ => egui::Color32::GRAY,
                    };
                    ui.label("状态");
                    ui.colored_label(phase_color, &st.phase_text);
                    ui.end_row();
                    ui.label("频道标识");
                    ui.label(&st.identifier);
                    ui.end_row();
                    ui.label("主播昵称");
                    ui.label(st.nickname.as_deref().unwrap_or("—"));
                    ui.end_row();
                    ui.label("输出目录");
                    ui.label(st.out_dir.as_ref().map(|p| p.display().to_string()).unwrap_or("—".into()));
                    ui.end_row();
                    ui.label("已写分段");
                    ui.label(st.segments_written.to_string());
                    ui.end_row();
                    ui.label("检测次数");
                    ui.label(st.detect_attempts.to_string());
                    ui.end_row();
                    ui.label("启动时间");
                    ui.label(st.started_at.as_deref().unwrap_or("—"));
                    ui.end_row();
                    ui.label("直播源");
                    ui.label(st.stream_hint.as_deref().unwrap_or("—"));
                    ui.end_row();
                });
            ui.add_space(6.0);
            if st.running {
                if ui.button("停止任务").clicked() {
                    task.stop();
                }
            }
            ui.separator();

            ui.label("日志");
            egui::ScrollArea::vertical()
                .id_salt("logs")
                .stick_to_bottom(true)
                .max_height(ui.available_height())
                .show(ui, |ui| {
                    let tail_start = task.lines.len().saturating_sub(800);
                    for line in &task.lines[tail_start..] {
                        ui.monospace(line);
                    }
                });
        });
    }

    fn ui_recordings(&mut self, ui: &mut egui::Ui) {
        egui::CentralPanel::default().show(ui, |ui| {
            ui.heading("录制文件");
            ui.label(format!(
                "目录：{}（共 {} 个文件，{}）",
                self.settings.recordings_dir,
                self.recordings.len(),
                human_size(self.rec_total_size)
            ));
            ui.horizontal(|ui| {
                ui.label("搜索");
                ui.add(
                    egui::TextEdit::singleline(&mut self.rec_search)
                        .hint_text("文件名过滤")
                        .desired_width(220.0),
                );
                if ui.button("刷新").clicked() {
                    self.reload_recordings();
                }
            });
            ui.separator();

            let mut to_delete: Option<usize> = None;
            let query = self.rec_search.trim().to_lowercase();
            egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
                for (i, file) in self.recordings.iter().enumerate() {
                    if !query.is_empty() && !file.rel.to_lowercase().contains(&query) {
                        continue;
                    }
                    ui.horizontal(|ui| {
                        ui.label(&file.rel);
                        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                            if ui.small_button("删除").clicked() {
                                to_delete = Some(i);
                            }
                            ui.label(human_size(file.size));
                        });
                    });
                }
            });
            if let Some(i) = to_delete {
                self.confirm_delete = Some(i);
            }
        });
    }

    fn ui_settings(&mut self, ctx: &egui::Context) {
        let mut open = self.settings_open;
        let mut apply = false;        egui::Window::new("设置")
            .open(&mut open)
            .collapsible(false)
            .resizable(false)
            .show(ctx, |ui| {
                egui::Grid::new("settings")
                    .num_columns(2)
                    .spacing([12.0, 8.0])
                    .show(ui, |ui| {
                        ui.label("录制目录");
                        ui.add(
                            egui::TextEdit::singleline(&mut self.settings.recordings_dir)
                                .desired_width(320.0),
                        );
                        ui.end_row();
                        ui.label("分段时长（秒）");
                        ui.add(egui::DragValue::new(&mut self.settings.segment_seconds).range(5..=86400));
                        ui.end_row();
                        ui.label("未开播重试间隔（秒）");
                        ui.add(egui::DragValue::new(&mut self.settings.detect_interval).range(1..=3600));
                        ui.end_row();
                        ui.label("断流重试间隔（秒）");
                        ui.add(egui::DragValue::new(&mut self.settings.break_seconds).range(1..=3600));
                        ui.end_row();
                        ui.label("Cookie 文件（Netscape）");
                        ui.add(
                            egui::TextEdit::singleline(&mut self.settings.cookies_path)
                                .hint_text("可选，留空则不携带")
                                .desired_width(320.0),
                        );
                        ui.end_row();
                    });
                ui.add_space(8.0);
                if ui.button("保存").clicked() {
                    apply = true;
                }
            });
        if apply {
            save_settings(&self.settings);
            self.settings_open = false;
        }
        if !open {
            self.settings_open = false;
        }
    }

    fn ui_confirm_delete(&mut self, ctx: &egui::Context) {
        let Some(i) = self.confirm_delete else { return };
        let Some(file) = self.recordings.get(i) else {
            self.confirm_delete = None;
            return;
        };
        let mut open = true;
        let mut confirmed = false;
        let mut cancel = false;
        egui::Window::new("确认删除")
            .open(&mut open)
            .collapsible(false)
            .resizable(false)
            .show(ctx, |ui| {
                ui.label(format!("确定删除 {}？此操作不可恢复。", file.rel));
                ui.add_space(6.0);
                ui.horizontal(|ui| {
                    if ui.button("取消").clicked() {
                        cancel = true;
                    }
                    if ui.button("删除").clicked() {
                        confirmed = true;
                    }
                });
            });
        if confirmed {
            let rel = file.rel.clone();
            let root = PathBuf::from(&self.settings.recordings_dir);
            let path = root.join(&rel);
            // 仅删除扫描到的录制目录内文件（rel 来自 read_dir 遍历，天然受限）。
            let _ = std::fs::remove_file(&path);
            self.reload_recordings();
        }
        if !open || cancel {
            self.confirm_delete = None;
        }
    }
}

impl eframe::App for DesktopApp {
    fn logic(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // 定期刷新（引擎线程推状态/日志，500ms 重绘一次足够）
        ctx.request_repaint_after(Duration::from_millis(500));
    }

    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        self.ui_top(ui);
        self.ui_sidebar(ui);
        match self.tab {
            Tab::Tasks => self.ui_task_detail(ui),
            Tab::Recordings => {
                // 每 5 秒自动刷新
                let stale = self
                    .rec_loaded_at
                    .map(|t| t.elapsed() > Duration::from_secs(5))
                    .unwrap_or(true);
                if stale {
                    self.reload_recordings();
                }
                self.ui_recordings(ui);
            }
        }
        let ctx = ui.ctx().clone();
        self.ui_settings(&ctx);
        self.ui_confirm_delete(&ctx);
    }
}

/// 从系统字体目录加载 CJK 字体（.ttc 集合，取第一个 face）。
fn install_cjk_font(ctx: &egui::Context) {
    const CANDIDATES: &[&str] = &[
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/System/Library/Fonts/PingFang.ttc",
        "C:\\Windows\\Fonts\\msyh.ttc",
    ];
    for path in CANDIDATES {
        let Ok(bytes) = std::fs::read(path) else { continue };
        let mut fonts = egui::FontDefinitions::default();
        fonts
            .font_data
            .insert("cjk".into(), Arc::new(egui::FontData::from_owned(bytes)));
        for family in [egui::FontFamily::Proportional, egui::FontFamily::Monospace] {
            fonts.families.entry(family).or_default().push("cjk".into());
        }
        ctx.set_fonts(fonts);
        eprintln!("dlr-desktop: 已加载 CJK 字体 {path}");
        return;
    }
    eprintln!("dlr-desktop: 未找到系统 CJK 字体，中文可能无法显示");
}

fn main() -> eframe::Result<()> {
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([1000.0, 660.0])
            .with_title(APP_TITLE),
        ..Default::default()
    };
    eframe::run_native(
        "dlr-desktop",
        options,
        Box::new(|cc| Ok(Box::new(DesktopApp::new(cc)))),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 系统 CJK 字体（.ttc 集合 face 0）必须能被 ab_glyph 解析且覆盖常用汉字；
    /// 否则桌面端中文会渲染成豆腐块。
    #[test]
    fn system_cjk_font_parses_with_glyphs() {
        let mut found = false;
        for path in [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/System/Library/Fonts/PingFang.ttc",
            "C:\\Windows\\Fonts\\msyh.ttc",
        ] {
            let Ok(bytes) = std::fs::read(path) else { continue };
            let Ok(font) = ab_glyph::FontVec::try_from_vec(bytes) else { continue };
            use ab_glyph::Font;
            // '录' (U+5F55) 与 '端' (U+7AEF)：界面核心词，必须可渲染
            for ch in ['录', '端', '任', '务', '停', '止'] {
                let glyph = font.glyph_id(ch);
                assert!(
                    glyph.0 != 0,
                    "字体 {path} 缺少字形：{ch}"
                );
            }
            found = true;
            break;
        }
        assert!(found, "未找到任何系统 CJK 字体");
    }
}
