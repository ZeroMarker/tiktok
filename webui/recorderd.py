"""录制控制面：独立进程托管全部录制引擎，WebUI 通过本地 unix socket 调用。

这是 ADR 0002 的落地：把「引擎宿主」从 WebUI 进程里拆出来。

- 重启 WebUI（改前端、调端口、升级）**不再打断正在进行的录制**；
- WebUI 崩溃/被 OOM kill 也不影响引擎；
- 两个服务各自有 systemd 生命周期、资源限制与重启策略；
- 任务目录（state/tasks.json）由本进程独占写入，WebUI 只通过控制 API 读写。

控制 API（仅本地 unix socket，JSON；路径见 config.RECORDERD_SOCKET）：

===============================  ==========================================
``GET  /health``                  ``{"ok": true, "tasks": N}``
``GET  /jobs``                    = ``jobs.list_jobs()``（运行中 + 暂停中）
``GET  /logs?unit=&tail=``        ``{"logs": "…"}``
``POST /start``                   ``{"unit": "…"}``（201）
``POST /pause`` ``/resume``       ``{"ok": true}`` / ``{"unit": "…"}``
``POST /restart`` ``/delete-task````{"ok": true}``
===============================  ==========================================

错误：400 ``{"error": …}``（校验/状态类，前端直接展示文案）；5xx 控制面内部错误。
"""

from __future__ import annotations

import json
import os
import signal
import socketserver
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# 直接以脚本执行时（systemd ExecStart），本模块不在包上下文中，
# 先把仓库根加入 sys.path 才能 import webui.*（与 app.py 同一约定）。
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webui import config, jobs  # noqa: E402

# 停止服务时给引擎的收尾时间（ffmpeg 收尾当前分段）；单元 TimeoutStopSec 需更大。
SHUTDOWN_TIMEOUT = 45.0


def prepare_socket_path() -> str:
    """准备 socket 路径：建目录（0700）、清掉上次异常退出留下的文件。"""
    path = Path(config.RECORDERD_SOCKET)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    return str(path)


class Handler(BaseHTTPRequestHandler):
    server_version = "LiveRecorderd/1.0"
    protocol_version = "HTTP/1.1"

    def address_string(self) -> str:  # noqa: D102 - AF_UNIX 的 client_address 是空串
        return "local"

    def log_message(self, fmt: str, *args: object) -> None:
        # 轮询频繁（WebUI 5s 一次）：默认静默，RECORDERD_VERBOSE=1 时打印。
        if os.environ.get("RECORDERD_VERBOSE"):
            print(f"recorderd - {fmt % args}", flush=True)

    def send_json(self, status: int, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/health":
                self.send_json(HTTPStatus.OK, {"ok": True, "tasks": len(jobs.list_jobs())})
            elif parsed.path == "/jobs":
                self.send_json(HTTPStatus.OK, jobs.list_jobs())
            elif parsed.path == "/logs":
                query = parse_qs(parsed.query)
                unit = query.get("unit", [""])[0]
                tail = int(query.get("tail", ["200"])[0] or "200")
                self.send_json(HTTPStatus.OK, {"logs": jobs.job_logs(unit, tail)})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, RuntimeError) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 — 控制面内部错误不能杀死服务
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": f"控制面内部错误：{exc}"})

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 16_384:
                raise ValueError("请求过大")
            data = json.loads(self.rfile.read(length) or b"{}")
            path = urlparse(self.path).path
            if path == "/start":
                self.send_json(HTTPStatus.CREATED, {"unit": jobs.start_job(data)})
            elif path == "/pause":
                jobs.pause_job(str(data.get("unit", "")))
                self.send_json(HTTPStatus.OK, {"ok": True})
            elif path == "/resume":
                self.send_json(HTTPStatus.OK, {"unit": jobs.resume_job(str(data.get("unit", "")))})
            elif path == "/restart":
                jobs.restart_job(str(data.get("unit", "")))
                self.send_json(HTTPStatus.OK, {"ok": True})
            elif path == "/delete-task":
                jobs.delete_job(str(data.get("unit", "")))
                self.send_json(HTTPStatus.OK, {"ok": True})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, RuntimeError, json.JSONDecodeError) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except Exception as exc:  # noqa: BLE001 — 同上
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": f"控制面内部错误：{exc}"})


class UnixHTTPServer(socketserver.ThreadingUnixStreamServer):
    """unix socket 上的线程化 HTTP 服务（不回落到 TCP，也不需要端口）。"""

    daemon_threads = True
    request_queue_size = 64
    server_name = "recorderd"  # BaseHTTPRequestHandler 需要这两个属性
    server_port = 0


def main() -> None:
    socket_path = prepare_socket_path()
    server = UnixHTTPServer(socket_path, Handler)
    try:
        os.chmod(socket_path, 0o600)
    except OSError:
        pass

    def _graceful(signum: int, _frame: object) -> None:
        print(f"recorderd 收到信号 {signum}，正在并行停止全部录制任务...", flush=True)
        jobs.shutdown_recorder(timeout=SHUTDOWN_TIMEOUT)
        try:
            server.server_close()
            Path(socket_path).unlink()
        except OSError:
            pass
        os._exit(0)

    signal.signal(signal.SIGTERM, _graceful)
    signal.signal(signal.SIGINT, _graceful)

    restored, failed = jobs.restore_jobs()
    if restored:
        print(f"已恢复 {len(restored)} 个录制任务：{', '.join(restored)}", flush=True)
    for unit, error in failed.items():
        print(f"恢复录制任务失败 {unit}：{error}", file=sys.stderr, flush=True)
    print(f"Live Recorderd: {socket_path}（{len(restored)} 个运行中任务）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        jobs.shutdown_recorder(timeout=SHUTDOWN_TIMEOUT)


if __name__ == "__main__":
    main()
