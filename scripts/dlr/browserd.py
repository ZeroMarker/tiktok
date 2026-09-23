"""browserd — 共享常驻 Chromium 渲染服务（CDP over --remote-debugging-pipe）。

所有录制引擎共用这一个 Chromium 实例渲染 TikTok 页面：把"每轮探测冷启动一个
浏览器"（曾 ~247 次/小时、≈0.5 核 CPU、每次全新指纹触发 WAF 挑战）降为"开一个
标签页"。

服务端:  python3 scripts/dlr/browserd.py --serve     (systemd: tiktok-browserd.service)
客户端:  from dlr.browserd import render_document
         render_document(url, timeout=…) -> str | None

HTTP 协议（默认 127.0.0.1:9555，TIKTOK_BROWSERD_URL 可覆盖）:
    GET  /health  -> 200 text/plain "ok"
    POST /render  body={"url": …, "timeout": …, "wait_js": …}
                  -> 200 text/html 渲染后的 DOM；服务不可用 -> 客户端拿到 None

渲染就绪条件: 客户端提供的 wait_js 表达式为真即取 DOM；到 deadline 仍不满足也
返回当前 DOM（与旧 `--dump-dom --virtual-time-budget=15000` 的语义一致）。
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

DEFAULT_URL = "http://127.0.0.1:9555"
DEFAULT_WAIT_JS = "document.readyState === 'complete'"
# 每条 CDP 消息以 NUL 结尾；DOM outerHTML 约几百 KB，给出宽松上限防脏数据。
_MAX_BUFFER = 128 * 1024 * 1024


class CDPError(RuntimeError):
    """CDP 调用失败（超时、协议错误、Chrome 已退出）。"""


def browserd_url() -> str:
    return os.environ.get("TIKTOK_BROWSERD_URL", DEFAULT_URL)


def _is_snap(binary: str) -> bool:
    """识别 Snap 可执行文件及 Ubuntu 的 chromium-browser Snap 跳转脚本。"""
    path = os.path.realpath(binary)
    if path.startswith("/snap/"):
        return True
    try:
        with open(path, encoding="utf-8", errors="ignore") as handle:
            return "/snap/bin/chromium" in handle.read(4096)
    except OSError:
        return False


def find_chrome() -> str | None:
    """选择 Chrome 可执行文件：显式配置 > 本机完整安装（非 Snap）> Snap。"""
    custom = os.environ.get("TIKTOK_BROWSERD_CHROME")
    if custom:
        return custom if os.path.exists(custom) else None
    fixed = "/opt/browser-desktop/chromium/chrome"
    if os.path.exists(fixed):
        return fixed
    candidates = [
        path
        for path in dict.fromkeys(
            shutil.which(name)
            for name in (
                "google-chrome",
                "google-chrome-stable",
                "chromium",
                "chromium-browser",
            )
        )
        if path
    ]
    return next((path for path in candidates if not _is_snap(path)), None) or (
        candidates[0] if candidates else None
    )


class Chrome:
    """通过 `--remote-debugging-pipe`（fd3 读 / fd4 写，NUL 分隔 JSON）驱动的单实例 Chrome。"""

    def __init__(self, binary: str, profile: str) -> None:
        self.binary = binary
        self.profile = profile
        self.pid: int | None = None
        self._cmd_w: int | None = None  # 父进程写（子进程 fd3）
        self._reply_r: int | None = None  # 父进程读（子进程 fd4）
        self._pending: dict[int, queue.Queue] = {}
        self._next_id = 0
        self._id_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._ensure_lock = threading.Lock()
        self._alive = threading.Event()
        self._stderr = sys.stderr

    # ---- 生命周期 ----

    def ensure(self) -> None:
        """Chrome 存活则不动；否则（重新）启动。线程安全。"""
        if self._alive.is_set() and self.pid:
            return
        with self._ensure_lock:
            if self._alive.is_set() and self.pid:
                return
            self._start_locked()

    def _start_locked(self) -> None:
        self.stop()
        os.makedirs(self.profile, exist_ok=True)
        to_r, to_w = os.pipe()  # 父写 -> 子读
        from_r, from_w = os.pipe()  # 子写 -> 父读
        pid = os.fork()
        if pid == 0:
            try:
                # 独立进程组：停止时可 killpg 兜底回收渲染子进程。
                os.setsid()
                # 与实验 H1 一致：Chrome 读 fd3、写 fd4。先复制到高位再落位，
                # 避免 pipe 端编号本身是 3/4 时被 dup2 互相覆盖。
                read_dup = os.dup(to_r)
                write_dup = os.dup(from_w)
                os.dup2(read_dup, 3)
                os.dup2(write_dup, 4)
                os.close(read_dup)
                os.close(write_dup)
                for fd in (to_r, to_w, from_r, from_w):
                    if fd > 4:
                        os.close(fd)
                os.execv(
                    self.binary,
                    [
                        self.binary,
                        "--headless=new",
                        "--no-sandbox",
                        "--disable-gpu",
                        "--disable-vulkan",
                        "--disable-features=Vulkan,VulkanFromANGLE,DefaultANGLEVulkan",
                        "--use-gl=disabled",
                        "--disable-software-rasterizer",
                        "--disable-gpu-compositing",
                        "--disable-dev-shm-usage",
                        "--no-first-run",
                        "--no-default-browser-check",
                        f"--user-data-dir={self.profile}",
                        "--remote-debugging-pipe",
                    ],
                )
            except BaseException:
                os._exit(127)
        # 父进程：关掉子端，保留 cmd 写端 / reply 读端
        os.close(to_r)
        os.close(from_w)
        self.pid = pid
        self._cmd_w = to_w
        self._reply_r = from_r
        self._pending.clear()
        self._alive.set()
        threading.Thread(target=self._read_loop, name="browserd-cdp", daemon=True).start()
        print(
            f"[browserd] chrome started pid={pid} binary={self.binary}",
            file=self._stderr,
            flush=True,
        )

    def stop(self) -> None:
        pid, self.pid = self.pid, None
        self._alive.clear()
        if pid is not None:
            # 先终止进程组让 reader 拿到 EOF 自行退出，再关父端 fd，
            # 避免 close 与阻塞 read 竞争留下僵死线程。
            for sig, grace in ((signal.SIGTERM, 3.0), (signal.SIGKILL, 1.0)):
                try:
                    os.killpg(pid, sig)
                except (ProcessLookupError, PermissionError):
                    try:
                        os.kill(pid, sig)
                    except ProcessLookupError:
                        break
                deadline = time.monotonic() + grace
                while time.monotonic() < deadline:
                    try:
                        done, _ = os.waitpid(pid, os.WNOHANG)
                    except ChildProcessError:
                        done = pid
                    if done:
                        break
                    time.sleep(0.05)
                else:
                    continue
                break
            try:
                os.waitpid(pid, os.WNOHANG)
            except ChildProcessError:
                pass
        for fd_name in ("_cmd_w", "_reply_r"):
            fd = getattr(self, fd_name)
            if fd is not None:
                setattr(self, fd_name, None)
                try:
                    os.close(fd)
                except OSError:
                    pass

    # ---- CDP 调用 ----

    def call(
        self,
        method: str,
        params: dict | None = None,
        *,
        session_id: str | None = None,
        timeout: float = 15.0,
    ) -> dict:
        if not self._alive.is_set():
            raise CDPError("chrome is not running")
        with self._id_lock:
            self._next_id += 1
            mid = self._next_id
        reply: queue.Queue = queue.Queue(maxsize=1)
        self._pending[mid] = reply
        message: dict = {"id": mid, "method": method}
        if params:
            message["params"] = params
        if session_id:
            message["sessionId"] = session_id
        try:
            with self._write_lock:
                if self._cmd_w is None:
                    raise CDPError("chrome pipe closed")
                os.write(self._cmd_w, json.dumps(message).encode("utf-8") + b"\0")
            try:
                response = reply.get(timeout=timeout)
            except queue.Empty as exc:
                raise CDPError(f"{method} timed out after {timeout:g}s") from exc
        finally:
            self._pending.pop(mid, None)
        if "error" in response:
            raise CDPError(f"{method}: {response['error']}")
        return response.get("result") or {}

    def _read_loop(self) -> None:
        reply_r = self._reply_r
        if reply_r is None:
            return
        buffer = b""
        while True:
            try:
                chunk = os.read(reply_r, 1 << 20)
            except OSError:
                chunk = b""
            if not chunk:
                # Chrome 退出：唤醒所有等待者，标记不存活供 ensure() 重启。
                self._alive.clear()
                dead = {"error": {"message": "chrome exited"}}
                for pending in list(self._pending.values()):
                    try:
                        pending.put_nowait(dead)
                    except queue.Full:
                        pass
                return
            buffer += chunk
            if len(buffer) > _MAX_BUFFER:
                buffer = buffer[-(_MAX_BUFFER // 2):]
            while b"\0" in buffer:
                raw, buffer = buffer.split(b"\0", 1)
                if not raw:
                    continue
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                mid = message.get("id")
                if mid is None:
                    continue  # 事件不关心
                pending = self._pending.get(mid)
                if pending is not None:
                    try:
                        pending.put_nowait(message)
                    except queue.Full:
                        pass


def render_page(
    chrome: Chrome,
    url: str,
    timeout: float = 20.0,
    wait_js: str | None = None,
) -> str:
    """在独立标签页渲染 url，等 wait_js 为真（或超时）后返回 documentElement.outerHTML。

    标签页在 finally 中关闭，失败路径也不泄漏；Chrome 意外退出时重启一次重试。
    """
    wait_expression = wait_js or DEFAULT_WAIT_JS

    def open_target() -> str:
        chrome.ensure()
        try:
            result = chrome.call("Target.createTarget", {"url": "about:blank"})
        except CDPError:
            chrome.ensure()  # 可能刚死：强制重启后重试一次
            result = chrome.call("Target.createTarget", {"url": "about:blank"})
        return result["targetId"]

    target = open_target()
    try:
        session = chrome.call(
            "Target.attachToTarget", {"targetId": target, "flatten": True}
        )["sessionId"]
        chrome.call("Page.enable", session_id=session)
        chrome.call("Runtime.enable", session_id=session)
        chrome.call("Page.navigate", {"url": url}, session_id=session, timeout=10)

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                state = chrome.call(
                    "Runtime.evaluate",
                    {"expression": wait_expression, "returnByValue": True},
                    session_id=session,
                    timeout=min(5.0, remaining),
                )
                if (state.get("result") or {}).get("value"):
                    break
            except CDPError:
                pass  # 页面还在挑战页/加载中，继续等到 deadline
            time.sleep(0.5)

        page = chrome.call(
            "Runtime.evaluate",
            {"expression": "document.documentElement.outerHTML", "returnByValue": True},
            session_id=session,
            timeout=10,
        )
        return str((page.get("result") or {}).get("value") or "")
    finally:
        try:
            chrome.call("Target.closeTarget", {"targetId": target}, timeout=5)
        except CDPError:
            pass


# ---- HTTP 服务端 ----

_CHROME: Chrome | None = None


class _Handler(BaseHTTPRequestHandler):
    server_version = "browserd"

    def log_message(self, *_args) -> None:
        pass  # 每轮探测都打访问日志会淹没 journal；错误由调用方打印

    def _reply(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 (http.server 命名约定)
        if self.path == "/health":
            self._reply(200, b"ok\n", "text/plain; charset=utf-8")
        else:
            self._reply(404, b"not found\n", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/render":
            self._reply(404, b"not found\n", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            if not 0 < length <= 64 * 1024:
                raise ValueError("bad content length")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            url = str(payload["url"])
            timeout = float(payload.get("timeout") or 20.0)
            wait_js = payload.get("wait_js") or None
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            self._reply(400, f"bad request: {exc}\n".encode(), "text/plain; charset=utf-8")
            return
        assert _CHROME is not None
        try:
            html = render_page(_CHROME, url, timeout=timeout, wait_js=wait_js)
        except CDPError as exc:
            print(f"[browserd] render failed: {exc}", file=sys.stderr, flush=True)
            self._reply(502, f"cdp error: {exc}\n".encode(), "text/plain; charset=utf-8")
            return
        self._reply(200, html.encode("utf-8"), "text/html; charset=utf-8")


# ---- 客户端 ----


def render_document(url: str, timeout: float = 20.0, wait_js: str | None = None) -> str | None:
    """请求守护进程渲染并返回 DOM；服务不可用/出错时返回 None（不抛异常）。"""
    payload = json.dumps(
        {"url": url, "timeout": timeout, "wait_js": wait_js}
    ).encode("utf-8")
    request = urllib.request.Request(
        browserd_url().rstrip("/") + "/render",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout + 10) as response:
            return response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[browserd] 渲染服务不可用：{exc}", file=sys.stderr, flush=True)
        return None


def main() -> int:
    if "--serve" not in sys.argv:
        print(f"用法: {sys.argv[0]} --serve", file=sys.stderr)
        return 2
    binary = find_chrome()
    if not binary:
        print("[browserd] 找不到可用的 Chrome/Chromium", file=sys.stderr)
        return 1
    profile = os.environ.get("TIKTOK_BROWSERD_PROFILE") or os.path.join(
        os.path.expanduser("~/.cache"), "tiktok-browserd", "profile"
    )
    global _CHROME
    _CHROME = Chrome(binary, profile)
    _CHROME.ensure()

    parts = urlsplit(browserd_url())
    host = parts.hostname or "127.0.0.1"
    port = parts.port or 9555
    server = ThreadingHTTPServer((host, port), _Handler)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    print(
        f"[browserd] listening on {host}:{port} chrome={binary} profile={profile}",
        flush=True,
    )
    try:
        server.serve_forever()
    finally:
        _CHROME.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
