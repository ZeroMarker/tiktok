"""WebUI → recorderd 的控制客户端（本地 unix socket + JSON）。

函数名与 ``jobs.py`` 对齐，因此 server/stats 只需把 ``jobs.x`` 换成 ``control.x``：

- ``jobs.py``   = 引擎宿主的实现（recorderd 进程内使用）；
- ``control.py``= 该实现的控制面客户端（WebUI 进程内使用）。

错误语义延续原单进程行为：校验/状态类错误抛 ``RuntimeError``（WebUI 映射 400，
前端 toast 直接显示服务端文案）；控制面不可达抛 ``ControlUnavailable``（WebUI 映射 503，
前端按「部分数据同步失败 + 重试」处理）。
"""

from __future__ import annotations

import http.client
import json
import socket
from urllib.parse import quote

from webui import config

# 轻查询与状态刷新
DEFAULT_TIMEOUT = 12.0
# 控制类操作（暂停/删除/重启）要等引擎收尾当前分段
CONTROL_TIMEOUT = 40.0


class ControlUnavailable(Exception):
    """录制控制面不可达：recorderd 未启动、socket 失效或内部错误。"""


class _UnixHTTPConnection(http.client.HTTPConnection):
    """把 http.client 连到 unix socket 上（标准库即可，无需额外依赖）。"""

    def __init__(self, socket_path: str, timeout: float) -> None:
        super().__init__("localhost", timeout=timeout)
        self._socket_path = socket_path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self._socket_path)
        except OSError as exc:
            sock.close()
            raise ControlUnavailable(f"录制服务不可用（{exc.strerror or exc}）") from exc
        self.sock = sock


def _request(method: str, path: str, payload: dict | None = None, timeout: float = DEFAULT_TIMEOUT):
    body = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"} if body else {}
    conn = _UnixHTTPConnection(config.RECORDERD_SOCKET, timeout)
    try:
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        status = response.status
    except ControlUnavailable:
        raise
    except (socket.timeout, TimeoutError) as exc:
        # 控制面没应答 = 不可用（而不是请求有错），WebUI 侧统一映射 503。
        raise ControlUnavailable("录制服务响应超时") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise ControlUnavailable(f"录制服务不可用（{exc}）") from exc
    finally:
        conn.close()
    try:
        data = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        data = {}
    if isinstance(data, dict) and data.get("error") and status >= 400:
        message = str(data["error"])
    else:
        message = f"录制服务返回异常（HTTP {status}）"
    if status >= 500:
        raise ControlUnavailable(message)
    if status >= 400:
        raise RuntimeError(message)
    return data


def health() -> bool:
    """控制面是否可达（用于 /api/health 与排障）。探针本身绝不抛异常。"""
    try:
        _request("GET", "/health", timeout=3.0)
        return True
    except Exception:  # noqa: BLE001 — 健康检查只报告可达性
        return False


def list_jobs() -> list[dict]:
    data = _request("GET", "/jobs")
    if not isinstance(data, list):
        raise ControlUnavailable("录制服务返回了异常的任务列表")
    return data


def start_job(data: dict) -> str:
    return str(_request("POST", "/start", data)["unit"])


def pause_job(unit: str) -> None:
    _request("POST", "/pause", {"unit": unit}, timeout=CONTROL_TIMEOUT)


def resume_job(unit: str) -> str:
    return str(_request("POST", "/resume", {"unit": unit}, timeout=CONTROL_TIMEOUT)["unit"])


def restart_job(unit: str) -> None:
    _request("POST", "/restart", {"unit": unit}, timeout=CONTROL_TIMEOUT)


def delete_job(unit: str) -> None:
    _request("POST", "/delete-task", {"unit": unit}, timeout=CONTROL_TIMEOUT)


def job_logs(unit: str, tail: int = 200) -> str:
    data = _request("GET", f"/logs?unit={quote(unit)}&tail={int(tail)}")
    return str(data.get("logs") or "")
