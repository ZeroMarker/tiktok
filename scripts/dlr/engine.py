"""统一录制引擎：输出布局、检测循环、ffmpeg 分段与优雅停止。

所有平台共用此引擎；平台差异（如何解析直播源、昵称）全部收在适配器里。
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from dlr.adapters import load_adapter

FFMPEG_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"
)


def sanitize_path_part(value: str) -> str:
    """清洗路径片段：保留可打印字符（含中文/日文/emoji 昵称），
    去控制字符、空白转下划线、替换文件名非法字符、限长 120。"""
    cleaned = "".join(ch for ch in value if ch.isprintable())
    cleaned = cleaned.strip()
    cleaned = re.sub(r'[\/\\:*?"<>|]', "_", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned).strip(" .")
    return cleaned[:120]


class Engine:
    """每频道一个实例，负责完整录制生命周期。"""

    def __init__(
        self,
        platform: str,
        target: str,
        recordings_dir: str,
        cookies: str | None = None,
        cookie_header: str | None = None,
        segment_seconds: int = 600,
        detect_interval: int = 60,
        break_seconds: int = 10,
        dir_watch_interval: int = 3,
    ) -> None:
        self.platform = platform
        self.recordings_root = Path(recordings_dir).expanduser().resolve()
        self.segment_seconds = segment_seconds
        self.detect_interval = detect_interval
        self.break_seconds = break_seconds
        self.dir_watch_interval = dir_watch_interval

        self.adapter = load_adapter(
            platform, target, cookies=cookies, cookie_header=cookie_header
        )
        self.identifier = self.adapter.identifier
        self.ffmpeg_proc: subprocess.Popen | None = None
        self._stopping = False
        self.nickname: str | None = None
        self.out_dir: Path | None = None

        # 优雅停止：SIGTERM/SIGINT 时先结束 ffmpeg 再退出（配合 KillMode=mixed）
        signal.signal(signal.SIGTERM, self._on_signal)
        signal.signal(signal.SIGINT, self._on_signal)

    @classmethod
    def from_args(cls, args) -> "Engine":
        recordings_dir = (
            args.recordings_dir or os.environ.get("RECORDINGS_DIR") or "./recordings"
        )
        return cls(
            args.platform,
            args.target,
            recordings_dir,
            cookies=args.cookies,
            cookie_header=args.cookie,
            segment_seconds=args.segment_seconds,
            detect_interval=args.detect_interval,
            break_seconds=args.break_seconds,
        )

    # ---- 信号处理 ----

    def _on_signal(self, signum: int, _frame) -> None:
        self._stopping = True
        print(f"收到信号 {signum}，正在停止录制...", flush=True)
        if self.ffmpeg_proc and self.ffmpeg_proc.poll() is None:
            self.ffmpeg_proc.terminate()
            try:
                self.ffmpeg_proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.ffmpeg_proc.kill()
        sys.exit(0)

    # ---- 生命周期 ----

    def run(self) -> int:
        print(f"开始无人值守录制 {self.platform}：{self.identifier}", flush=True)

        self.nickname = self._safe_nickname()
        if self.nickname:
            print(f"主播昵称：{self.nickname}", flush=True)
        else:
            print("未获取到昵称，输出目录将只使用频道标识（后续会尝试补获取）。", flush=True)

        self.out_dir = self.output_dir(self.nickname)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        log_dir = self.recordings_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        print(f"每 {self.segment_seconds} 秒生成一个分段", flush=True)
        print(f"输出目录：{self.out_dir}", flush=True)

        while not self._stopping:
            # 未开播轮询期间补获取昵称（仅当首次失败时才有动作）
            self._refresh_nickname()

            print(
                f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 尝试抓取直播源 @{self.identifier} ...",
                flush=True,
            )
            stream_url = self.adapter.detect_stream_url()
            if not stream_url:
                reason = getattr(self.adapter, "last_detect_error", None)
                if reason:
                    print(
                        f"  → 未获取到直播源：{reason}（等待 {self.detect_interval} 秒后重试）",
                        flush=True,
                    )
                else:
                    print(
                        f"  → 直播未开启 / 抓取失败，等待 {self.detect_interval} 秒后重试...",
                        flush=True,
                    )
                time.sleep(self.detect_interval)
                continue

            # 只打印去掉签名参数的开头，避免整串 token 进日志
            print(f"  → 成功抓到直播源：{stream_url.split('?')[0]}", flush=True)
            # 开播前最后补一次昵称：直播已确认时此路径对部分平台更可靠，
            # 成功则本场录制直接用昵称目录（不影响已开始的检测）。
            if not self.nickname:
                self._refresh_nickname()
            print("开始录制...", flush=True)
            self._record(self.out_dir, log_dir, stream_url, self.nickname)
            print(
                f"录制中断，等待 {self.break_seconds} 秒后重新抓取源...",
                flush=True,
            )
            if not self._stopping:
                time.sleep(self.break_seconds)

        return 0

    # ---- 内部 ----

    def _safe_nickname(self) -> str | None:
        try:
            return self.adapter.get_nickname()
        except Exception as exc:  # 昵称失败不影响录制
            print(f"获取昵称失败：{exc}", file=sys.stderr, flush=True)
            return None

    def _refresh_nickname(self) -> None:
        """首次昵称获取失败时，在未开播轮询期间补获取（不影响已开始的录制）。"""
        if self.nickname:
            return
        nickname = self._safe_nickname()
        if not nickname:
            return
        self.nickname = nickname
        new_dir = self.output_dir(nickname)
        new_dir.mkdir(parents=True, exist_ok=True)
        self.out_dir = new_dir
        print(f"补获取到主播昵称：{nickname}，新输出目录：{self.out_dir}", flush=True)

    # ---- 目录健壮性：输出目录被删除时自动重建 ----

    @staticmethod
    def _ensure_dir(path: Path) -> None:
        """确保目录存在（含父目录）。目录可能被外部清理（如 WebUI 删除/手动删空目录）。"""
        if not path.is_dir():
            path.mkdir(parents=True, exist_ok=True)

    def _watch_dir(self, path: Path, stop: threading.Event) -> None:
        """后台守护线程：录制期间定期检查输出目录，被删则立即重建。

        删除目录不影响已打开的分段文件句柄，但会让下一次分段写盘失败；
        这里在 ffmpeg 写下一个分段前把目录补回来，保证整场录制不中断。
        """
        while not stop.wait(self.dir_watch_interval):
            try:
                if not path.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                    print(f"检测到输出目录被删除，已自动重建：{path}", flush=True)
            except Exception as exc:
                print(f"重建输出目录失败：{exc}", file=sys.stderr, flush=True)

    def _name_parts(self, nickname: str | None) -> list[str]:
        """输出目录/文件名的公共片段：频道标识[_昵称]（平台已作为顶层目录）。"""
        parts = [self.identifier]
        if nickname:
            safe = sanitize_path_part(nickname)
            if safe and safe != self.identifier:
                parts.append(safe)
        return parts

    def output_dir(self, nickname: str | None) -> Path:
        return self.recordings_root / self.platform / "_".join(self._name_parts(nickname))

    def log_file(self, log_dir: Path, date: str, nickname: str | None = None) -> Path:
        """ffmpeg 日志路径：logs/<平台>/ffmpeg_record_<频道标识>[_昵称]_<日期>.log。"""
        prefix = "_".join(self._name_parts(nickname))
        return log_dir / self.platform / f"ffmpeg_record_{prefix}_{date}.log"

    def _record(
        self,
        out_dir: Path,
        log_dir: Path,
        stream_url: str,
        nickname: str | None = None,
    ) -> None:
        prefix = "_".join(self._name_parts(nickname))
        date = datetime.now().strftime("%Y%m%d")
        log_file = self.log_file(log_dir, date, nickname)
        output_pattern = str(out_dir / f"{prefix}_%Y%m%d_%H%M%S.mp4")

        # 健壮性：目录可能在循环等待期间被外部删除，启动前再次确保存在；
        # 任一目录创建失败则放弃本回合，由外层循环重试，不中断监控。
        try:
            self._ensure_dir(out_dir)
            self._ensure_dir(log_file.parent)
        except Exception as exc:
            print(
                f"创建输出/日志目录失败，本轮回合放弃：{exc}", file=sys.stderr, flush=True
            )
            return

        cmd = [
            "ffmpeg",
            "-nostdin",
            "-fflags", "+discardcorrupt",
            "-headers",
            f"User-Agent: {FFMPEG_UA}\r\nReferer: {self.adapter.referer}\r\n",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "30",
            "-rw_timeout", "30000000",
            "-i", stream_url,
            "-c", "copy",
        ]
        if self.adapter.bsf_aac:
            cmd += ["-bsf:a", "aac_adtstoasc"]
        cmd += [
            "-map", "0:v:0",
            "-map", "0:a:0?",
            "-f", "segment",
            "-segment_time", str(self.segment_seconds),
            "-segment_format", "mp4",
            "-reset_timestamps", "1",
            "-strftime", "1",
            output_pattern,
        ]

        # 录制全程由守护线程盯着输出目录：中途被删也能在下个分段前重建。
        stop = threading.Event()
        watcher = threading.Thread(
            target=self._watch_dir,
            args=(out_dir, stop),
            name=f"dirwatch-{self.identifier}",
            daemon=True,
        )
        watcher.start()

        proc: subprocess.Popen | None = None
        try:
            with open(log_file, "ab") as log_fh:
                proc = subprocess.Popen(cmd, stdout=log_fh, stderr=log_fh)
            self.ffmpeg_proc = proc
            rc = proc.wait()
        except Exception as exc:
            # 启动或运行期的异常（如日志文件无法打开）不应压垮监控循环
            print(f"录制回合异常：{exc}，即将重试...", file=sys.stderr, flush=True)
            rc = -1
        finally:
            stop.set()
            watcher.join(timeout=self.dir_watch_interval + 1)
            self.ffmpeg_proc = None

        if rc != 0:
            print(f"ffmpeg 异常退出（rc={rc}，源可能已断），即将重试...", flush=True)
