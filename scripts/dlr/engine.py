"""统一录制引擎：输出布局、检测循环、ffmpeg 分段与优雅停止。

所有平台共用此引擎；平台差异（如何解析直播源、昵称）全部收在适配器里。
"""

from __future__ import annotations

import os
import random
import re
import signal
import shutil
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


def _kill_isolated_child_process_groups() -> None:
    """Kill direct children that detached into their own process groups.

    Snap launchers can escape a transient unit when the engine uses os._exit()
    from a signal handler. Chromium probes are started in a new session, so
    terminating those child groups prevents orphan browsers and profiles.
    """
    children_path = Path(f"/proc/{os.getpid()}/task/{os.getpid()}/children")
    try:
        child_pids = children_path.read_text().split()
    except OSError:
        return

    own_pgid = os.getpgrp()
    child_pgids: set[int] = set()
    child_profiles: set[Path] = set()
    for child_pid in child_pids:
        try:
            args = Path(f"/proc/{child_pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            args = []
        for arg in args:
            if not arg.startswith(b"--user-data-dir="):
                continue
            profile = Path(os.fsdecode(arg.partition(b"=")[2]))
            if (
                profile.name.startswith("tiktok-chromium-")
                and profile.parent.name == "chromium-headless"
            ):
                child_profiles.add(profile)
        try:
            pgid = os.getpgid(int(child_pid))
        except (ProcessLookupError, ValueError):
            continue
        if pgid != own_pgid:
            child_pgids.add(pgid)

    for pgid in child_pgids:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    # SIGKILL delivery is asynchronous. A short retry removes the exact
    # disposable profiles after Chromium has stopped writing into them.
    for _attempt in range(2):
        for profile in child_profiles:
            shutil.rmtree(profile, ignore_errors=True)
        if not any(profile.exists() for profile in child_profiles):
            break
        time.sleep(0.1)


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
        detect_interval: int = 210,
        detect_jitter: int = 0,
        break_seconds: int = 10,
        dir_watch_interval: int = 3,
        quality: str = "best",
        nickname_attempts: int = 3,
        nickname_retry_delay: float = 3.0,
    ) -> None:
        self.platform = platform
        self.recordings_root = Path(recordings_dir).expanduser().resolve()
        self.segment_seconds = segment_seconds
        if detect_interval < 1:
            raise ValueError("detect_interval 必须大于 0")
        if detect_jitter < 0 or detect_jitter >= detect_interval:
            raise ValueError("detect_jitter 必须大于等于 0 且小于 detect_interval")
        self.detect_interval = detect_interval
        self.detect_jitter = detect_jitter
        self.break_seconds = break_seconds
        self.dir_watch_interval = dir_watch_interval
        if nickname_attempts < 1:
            raise ValueError("nickname_attempts 必须大于 0")
        if nickname_retry_delay < 0:
            raise ValueError("nickname_retry_delay 不能为负数")
        # 昵称决定输出目录名：多试几次再回退，避免"这场取到、下场没取到"的目录分裂。
        self.nickname_attempts = nickname_attempts
        self.nickname_retry_delay = nickname_retry_delay

        self.adapter = load_adapter(
            platform, target, cookies=cookies, cookie_header=cookie_header, quality=quality
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
            detect_jitter=args.detect_jitter,
            break_seconds=args.break_seconds,
            quality=args.quality,
        )

    # ---- 信号处理 ----

    def _on_signal(self, signum: int, _frame) -> None:
        """SIGTERM/SIGINT：先让 ffmpeg 收尾当前分段，再立即结束进程。

        信号处理器经常在 curl_cffi / subprocess 的 C 回调栈里执行，此处 `sys.exit()`
        抛出的 SystemExit 会被 C 层吞掉（"Exception ignored from cffi callback"），
        进程随后继续检测轮询，直到 systemd `TimeoutStopSec`（30s）到期被 SIGKILL ——
        WebUI 的停止请求因此超时，看起来"停不下来"。ffmpeg 已收尾后直接 os._exit，
        保证停止立即生效。
        """
        self._stopping = True
        # Buffered stdout/stderr may already be executing when Python dispatches
        # the signal from a C callback. Re-entering print()/flush() then raises
        # RuntimeError before os._exit(), so use an unbuffered file-descriptor
        # write and keep shutdown independent from Python's IO wrappers.
        try:
            os.write(2, f"收到信号 {signum}，正在停止录制...\n".encode())
        except OSError:
            pass
        proc = self.ffmpeg_proc
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        _kill_isolated_child_process_groups()
        os._exit(0)

    # ---- 生命周期 ----

    def run(self) -> int:
        print(f"开始无人值守录制 {self.platform}：{self.identifier}", flush=True)

        # 不在启动时解析昵称/创建输出目录：此时可能尚未开播，昵称常解析失败，
        # 先建只会留下"无昵称"空目录。输出目录推迟到开播确认后创建（见下方）。
        log_dir = self.recordings_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        print(f"每 {self.segment_seconds} 秒生成一个分段", flush=True)
        print(
            "未开播检测间隔："
            f"{self.detect_interval - self.detect_jitter}–"
            f"{self.detect_interval + self.detect_jitter} 秒（随机抖动）",
            flush=True,
        )

        while not self._stopping:
            try:
                print(
                    f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 尝试抓取直播源 @{self.identifier} ...",
                    flush=True,
                )
                stream_url = self.adapter.detect_stream_url()
                if not stream_url:
                    delay = self._next_detect_delay()
                    reason = getattr(self.adapter, "last_detect_error", None)
                    if reason:
                        print(
                            f"  → 未获取到直播源：{reason}（等待 {delay} 秒后重试）",
                            flush=True,
                        )
                    else:
                        print(
                            f"  → 直播未开启 / 抓取失败，等待 {delay} 秒后重试...",
                            flush=True,
                        )
                    time.sleep(delay)
                    continue

                # 只打印去掉签名参数的开头，避免整串 token 进日志
                print(f"  → 成功抓到直播源：{stream_url.split('?')[0]}", flush=True)
                # 开播确认后再补一次昵称：此时直播页 live 数据齐全，最可靠。
                # 成功则本场录制直接用昵称目录；失败则回退为仅频道标识目录。
                # 目录一旦定下就不再改名：本场后续回合若才取到昵称，也不能
                # 换目录名，否则同一场录制会分裂出 <slug> 和 <slug>_<昵称> 两处。
                if self.out_dir is None:
                    self._refresh_nickname()

                # 开播确认后才创建输出目录，避免"先无昵称、后有昵称"的双目录残留。
                out_dir = self.output_dir(self.nickname)
                try:
                    out_dir.mkdir(parents=True, exist_ok=True)
                except Exception as exc:
                    print(
                        f"创建输出目录失败，本轮回合放弃：{exc}",
                        file=sys.stderr,
                        flush=True,
                    )
                    time.sleep(self.break_seconds)
                    continue
                self.out_dir = out_dir
                print(f"输出目录：{self.out_dir}", flush=True)

                print("开始录制...", flush=True)
                self._record(self.out_dir, log_dir, stream_url, self.nickname)
                print(
                    f"录制中断，等待 {self.break_seconds} 秒后重新抓取源...",
                    flush=True,
                )
                if not self._stopping:
                    time.sleep(self.break_seconds)
            except Exception as exc:
                # 单次检测/录制回合的异常不应压垮监控循环：记录后继续下一轮回合。
                print(
                    f"[{self.platform}] 检测回合异常：{exc}",
                    file=sys.stderr,
                    flush=True,
                )
                if not self._stopping:
                    time.sleep(self._next_detect_delay())

        return 0

    # ---- 内部 ----

    def _next_detect_delay(self) -> int:
        """返回带随机抖动的下一次离线检测等待时间。"""
        if not self.detect_jitter:
            return self.detect_interval
        return random.randint(
            self.detect_interval - self.detect_jitter,
            self.detect_interval + self.detect_jitter,
        )

    def _safe_nickname(self) -> str | None:
        try:
            return self.adapter.get_nickname()
        except Exception as exc:  # 昵称失败不影响录制
            print(f"获取昵称失败：{exc}", file=sys.stderr, flush=True)
            return None

    def _refresh_nickname(self) -> None:
        """补取主播昵称：只更新 self.nickname，不创建/切换目录。

        目录统一在 run() 开播确认后创建（此时昵称已定），避免轮询期间先建
        无昵称目录、补取后再建昵称目录的双目录残留。

        昵称直接决定目录名，一次抓取失败就会让同一频道分裂成
        `<slug>` 和 `<slug>_<昵称>` 两个目录，所以这里按 nickname_attempts
        重试（间隔 nickname_retry_delay 秒）；全部失败才回退为纯 slug 目录。
        """
        if self.nickname:
            return
        for attempt in range(1, self.nickname_attempts + 1):
            nickname = self._safe_nickname()
            if nickname:
                self.nickname = nickname
                print(f"获取到主播昵称：{nickname}", flush=True)
                return
            if attempt < self.nickname_attempts:
                print(
                    f"  → 昵称未取到（{attempt}/{self.nickname_attempts}），"
                    f"{self.nickname_retry_delay:g} 秒后重试...",
                    flush=True,
                )
                time.sleep(self.nickname_retry_delay)
        print(
            f"  → 昵称获取失败（已重试 {self.nickname_attempts} 次），"
            "输出目录回退为纯频道标识",
            flush=True,
        )

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
