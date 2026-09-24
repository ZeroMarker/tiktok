"""单进程录制调度器：所有频道的 Engine 跑在本进程的 daemon 线程里。

替代原先"每频道一个 systemd 临时单元"（systemd-run --collect）的多进程模式：

- 任务 = 一个线程 + 其引擎；引擎异常退出按 10 秒退避自动重启
  （等价原先 transient unit 的 ``Restart=on-failure RestartSec=10s``）。
- 状态、日志、生命周期全部进程内可查，WebUI 直接读取，
  不再需要 systemctl / journalctl / /proc 进程树扫描。
- 进程收到 SIGTERM/SIGINT 时由宿主统一 request_stop 所有引擎：
  ffmpeg 并发收尾当前分段后退出（等价原先 ``KillMode=mixed`` 的语义）。
- 依赖（yt-dlp / curl_cffi / 默认 Cookie 文件）按 record.sh 的既有约定解析；
  进程以 ubuntu 运行时用户站点原生可用，无需再桥接 PYTHONPATH。
"""

from __future__ import annotations

import os
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = str(PROJECT_ROOT / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from dlr.engine import Engine  # noqa: E402

from webui import config  # noqa: E402

# 各平台默认 Cookie 文件（等价各 record.sh 的 DEFAULT_COOKIE 约定；
# 任务显式携带 cookie_file 时优先）。
DEFAULT_COOKIES = {"tiktok": "cookies.txt", "soop": "soop-cookies.txt"}

# 引擎日志：recordings/logs/<平台>/engine_<unit>.log（WebUI 日志面板按 unit 读取）
LOG_PREFIX = "engine_"


def engine_log_path(recordings_dir: str, platform: str, unit: str) -> Path:
    return Path(recordings_dir).expanduser() / "logs" / platform / f"{LOG_PREFIX}{unit}.log"


def build_engine(unit: str, spec: dict) -> Engine:
    """按任务参数构建引擎（独立函数：测试可替换整个工厂）。

    参数语义与各平台 record.sh → dlr.py 的默认值保持一致
    （segment=600、detect=210±90、break=10、默认 Cookie 文件自动附带）。
    """
    platform = str(spec["platform"]).lower()
    target = str(spec["target"]).strip()
    cookie_file = str(spec.get("cookie_file", "") or "").strip()
    if not cookie_file:
        default_name = DEFAULT_COOKIES.get(platform)
        if default_name:
            default_path = PROJECT_ROOT / default_name
            if default_path.is_file():
                cookie_file = str(default_path)

    log_path = engine_log_path(config.RECORDINGS_DIR, platform, unit)
    # 每行即时落盘（开-追加-关）：避免任务反复重启泄漏文件句柄。
    # 同时带频道前缀镜像到进程 stdout（journal），便于运维侧整体回看。
    tee = f"[{platform}:{target}]"

    def sink(text: str) -> None:
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {text}"
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass
        print(f"{tee} {line}", flush=True)

    return Engine(
        platform,
        target,
        recordings_dir=config.RECORDINGS_DIR,
        cookies=cookie_file or None,
        segment_seconds=600,
        detect_interval=210,
        detect_jitter=90,
        break_seconds=10,
        quality=str(spec.get("quality", "best") or "best"),
        log_sink=sink,
    )


class _Task:
    """一个录制任务的运行时状态（目录/参数持久化仍由 jobs 的任务目录负责）。"""

    __slots__ = ("unit", "spec", "thread", "engine", "stop", "started_at", "restarts", "last_error")

    def __init__(self, unit: str, spec: dict) -> None:
        self.unit = unit
        self.spec = dict(spec)
        self.thread: threading.Thread | None = None
        self.engine: Engine | None = None
        self.stop = threading.Event()  # 任务级停止位（引擎停止 + 线程退出共用）
        self.started_at = time.time()
        self.restarts = 0
        self.last_error = ""


class Recorder:
    """任务线程的生命周期管理与状态汇总。所有公开方法线程安全。"""

    def __init__(self, restart_backoff: float = 10.0, log_tail_cap: int = 5000) -> None:
        self._lock = threading.RLock()
        self._tasks: dict[str, _Task] = {}
        self.restart_backoff = restart_backoff
        self.log_tail_cap = log_tail_cap

    # ---- 生命周期 ----

    def start(self, unit: str, spec: dict) -> None:
        """启动任务线程。已在运行时抛 RuntimeError（调用方负责给出用户文案）。"""
        with self._lock:
            existing = self._tasks.get(unit)
            if existing is not None and not existing.stop.is_set() \
                    and existing.thread is not None and existing.thread.is_alive():
                raise RuntimeError("任务已在运行")
            task = _Task(unit, spec)
            task.thread = threading.Thread(
                target=self._run, args=(task,), name=f"rec-{unit}", daemon=True
            )
            self._tasks[unit] = task
            task.thread.start()

    def _run(self, task: _Task) -> None:
        """引擎宿主循环：构建 → 运行 → 异常/意外退出按退避重启（等价 Restart=on-failure）。"""
        attempts = 0
        while not task.stop.is_set():
            if attempts:
                task.restarts = attempts
                if task.stop.wait(self.restart_backoff):
                    break
            attempts += 1
            try:
                engine = build_engine(task.unit, task.spec)
            except Exception as exc:  # noqa: BLE001 — 构建失败不能杀死线程/进程
                task.last_error = f"引擎构建失败：{exc}"
                continue
            with self._lock:
                if task.stop.is_set():
                    break
                task.engine = engine
            try:
                engine.run()
            except Exception as exc:  # noqa: BLE001 — 同上（等价单元崩溃）
                task.last_error = f"引擎异常退出：{exc}"
            finally:
                with self._lock:
                    if task.engine is engine:
                        task.engine = None
            if task.stop.is_set():
                task.last_error = ""
                break
            if not task.last_error:
                task.last_error = "引擎意外退出，自动重启中"
        # 线程收尾：因 stop 结束时清空错误（干净停止不算失败），并把自己从
        # 任务表摘除（短 join 超时后的后台收尾不能依赖状态轮询来清理）。
        if task.stop.is_set():
            task.last_error = ""
        with self._lock:
            if self._tasks.get(task.unit) is task:
                del self._tasks[task.unit]

    def stop(self, unit: str, timeout: float = 5.0) -> bool:
        """优雅停止任务（ffmpeg 收尾当前分段）。

        短 join：request_stop 已同步向 ffmpeg 发终止信号，分段收尾与线程退出
        都不依赖这里的等待——若线程正阻在网络调用里（页面抓取可达 20s），
        join 超时后线程在后台自行退出（停止位已置，状态接口已隐藏，不阻塞 API）。
        返回 False 仅表示线程尚未退出。"""
        with self._lock:
            task = self._tasks.get(unit)
            if task is None:
                return True
            engine = task.engine
            task.stop.set()
        if engine is not None:
            engine.request_stop()
        thread = task.thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)
        alive = thread is not None and thread.is_alive()
        if not alive:
            with self._lock:
                if self._tasks.get(unit) is task:
                    del self._tasks[unit]
        return not alive

    def restart(self, unit: str) -> None:
        """手动重启：停旧线程并以原参数拉起新线程（重启计数归零）。"""
        with self._lock:
            task = self._tasks.get(unit)
            if task is None:
                raise ValueError("任务未在运行")
            spec = dict(task.spec)
        self.stop(unit)
        self.start(unit, spec)

    def shutdown(self, timeout: float = 25.0) -> None:
        """进程退出前并行停止全部任务（先全员 request_stop，再统一 join）。"""
        with self._lock:
            tasks = list(self._tasks.values())
        for task in tasks:
            task.stop.set()
            engine = task.engine
            if engine is not None:
                engine.request_stop()
        deadline = time.monotonic() + timeout
        for task in tasks:
            thread = task.thread
            if thread is None or thread is threading.current_thread():
                continue
            thread.join(max(0.0, deadline - time.monotonic()))
        with self._lock:
            self._tasks.clear()

    # ---- 查询 ----

    def get_spec(self, unit: str) -> dict | None:
        with self._lock:
            task = self._tasks.get(unit)
            return dict(task.spec) if task else None

    def is_running(self, unit: str) -> bool:
        with self._lock:
            task = self._tasks.get(unit)
            if task is None or task.stop.is_set():
                return False
            return task.thread is not None and task.thread.is_alive()

    def running_units(self) -> set[str]:
        with self._lock:
            return {
                unit for unit, task in self._tasks.items()
                if not task.stop.is_set() and task.thread is not None and task.thread.is_alive()
            }

    def status(self) -> list[dict[str, object]]:
        """任务运行状态快照（字段与旧 systemctl show 聚合保持一致，前端零改动）。"""
        with self._lock:
            items = list(self._tasks.items())
            rss = _rss_bytes()
            pid = os.getpid()
        out: list[dict[str, object]] = []
        pruned: list[str] = []
        for unit, task in items:
            if task.stop.is_set():
                # 停止中的任务对状态接口隐藏（暂停/删除期间不闪烁成"运行中"）；
                # 线程已退出的直接清理，仍在收尾的等 stop()/下次查询处理。
                thread = task.thread
                if thread is None or not thread.is_alive():
                    pruned.append(unit)
                continue
            with self._lock:
                engine = task.engine
                alive = task.thread is not None and task.thread.is_alive()
            spec = task.spec
            platform = str(spec.get("platform", "unknown"))
            target = str(spec.get("target", ""))
            if not alive:
                state, substate, live = "failed", "failed", "offline"
            elif engine is None:
                # 构建/退避重启窗口（等价 transient unit 的 activating）
                state, substate, live = "active", "activating", "waiting"
            elif engine.phase == "stopping":
                state, substate, live = "active", "deactivating", "waiting"
            else:
                state, substate = "active", "running"
                live = "live" if (engine.phase == "recording" and engine.is_recording) else "waiting"
            out.append(
                {
                    "unit": unit,
                    "state": state,
                    "substate": substate,
                    "description": f"Live recorder: {platform} {target}",
                    "started": time.strftime(
                        "%a %Y-%m-%d %H:%M:%S %Z", time.localtime(task.started_at)
                    ),
                    "platform": platform,
                    "target": target,
                    "pid": pid,
                    "memory": rss,
                    "restarts": task.restarts,
                    "live": live,
                    "quality": spec.get("quality", "best"),
                }
            )
        if pruned:
            with self._lock:
                for unit in pruned:
                    task = self._tasks.get(unit)
                    if task is not None and task.stop.is_set():
                        thread = task.thread
                        if thread is None or not thread.is_alive():
                            del self._tasks[unit]
        return out

    # ---- 日志 ----

    def tail_log(self, recordings_dir: str, platform: str, unit: str, tail: int) -> str:
        """读取任务引擎日志的最后 tail 行（上限 log_tail_cap 行 / 100KB）。"""
        path = engine_log_path(recordings_dir, platform, unit)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines: deque[str] = deque(fh, maxlen=max(1, tail))
        except OSError:
            return ""
        return "".join(lines)[-100_000:]


def _rss_bytes() -> int:
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) * 1024
    except (OSError, IndexError, ValueError):
        pass
    return 0
