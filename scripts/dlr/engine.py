"""统一录制引擎：输出布局、检测循环、ffmpeg 分段与优雅停止。

所有平台共用此引擎；平台差异（如何解析直播源、昵称）全部收在适配器里。
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
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
    ) -> None:
        self.platform = platform
        self.recordings_root = Path(recordings_dir).expanduser().resolve()
        self.segment_seconds = segment_seconds
        self.detect_interval = detect_interval
        self.break_seconds = break_seconds

        self.adapter = load_adapter(
            platform, target, cookies=cookies, cookie_header=cookie_header
        )
        self.identifier = self.adapter.identifier
        self.ffmpeg_proc: subprocess.Popen | None = None
        self._stopping = False

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

        nickname = self._safe_nickname()
        if nickname:
            print(f"主播昵称：{nickname}", flush=True)
        else:
            print("未获取到昵称，输出目录将只使用频道标识。", flush=True)

        out_dir = self.output_dir(nickname)
        out_dir.mkdir(parents=True, exist_ok=True)
        log_dir = self.recordings_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        print(f"每 {self.segment_seconds} 秒生成一个分段", flush=True)
        print(f"输出目录：{out_dir}", flush=True)

        while not self._stopping:
            print(
                f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 尝试抓取直播源 @{self.identifier} ...",
                flush=True,
            )
            stream_url = self.adapter.detect_stream_url()
            if not stream_url:
                print(
                    f"  → 直播未开启 / 抓取失败，等待 {self.detect_interval} 秒后重试...",
                    flush=True,
                )
                time.sleep(self.detect_interval)
                continue

            # 只打印去掉签名参数的开头，避免整串 token 进日志
            print(f"  → 成功抓到直播源：{stream_url.split('?')[0]}", flush=True)
            print("开始录制...", flush=True)
            self._record(out_dir, log_dir, stream_url, nickname)
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

    def _name_parts(self, nickname: str | None) -> list[str]:
        """输出目录/文件名的公共前缀片段：平台_频道标识[_昵称]。"""
        parts = [f"{self.platform}_{self.identifier}"]
        if nickname:
            safe = sanitize_path_part(nickname)
            if safe and safe != self.identifier:
                parts.append(safe)
        return parts

    def output_dir(self, nickname: str | None) -> Path:
        return self.recordings_root / "_".join(self._name_parts(nickname))

    def _record(
        self,
        out_dir: Path,
        log_dir: Path,
        stream_url: str,
        nickname: str | None = None,
    ) -> None:
        prefix = "_".join(self._name_parts(nickname))
        date = datetime.now().strftime("%Y%m%d")
        log_file = log_dir / f"ffmpeg_record_{prefix}_{date}.log"
        output_pattern = str(out_dir / f"{prefix}_%Y%m%d_%H%M%S.mp4")

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

        with open(log_file, "ab") as log_fh:
            proc = subprocess.Popen(cmd, stdout=log_fh, stderr=log_fh)
        self.ffmpeg_proc = proc
        rc = proc.wait()
        self.ffmpeg_proc = None
        if rc != 0:
            print(f"ffmpeg 异常退出（rc={rc}，源可能已断），即将重试...", flush=True)
