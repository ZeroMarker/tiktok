"""HTTP 层：Handler（JSON API + 静态资源 + 录制文件下载）与服务入口。

路由只做协议与参数编解码：

- 任务状态与控制 → 转发给录制控制面 ``control``（→ recorderd 进程，见 ADR 0002）；
- 录制文件与系统概览 → ``files`` / ``stats``（本进程内的文件系统视图）。

静态资源分两类：
- PWA 白名单（``STATIC_FILES``，如 manifest/sw/图标）；
- 前端源码与依赖目录（``STATIC_PREFIXES``：``/frontend/`` 原生 ESM 应用、
  ``/vendor/`` 本地 lit@3）——无构建链，源码即产物。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from webui import config, control, files, stats

# Static PWA assets served by the web UI.  Only whitelisted names, served
# from webui/ with explicit content types.
STATIC_FILES: dict[str, tuple[str, str]] = {
    "favicon.ico": ("image/x-icon", "public, max-age=604800"),
    "icon-32.png": ("image/png", "public, max-age=604800"),
    "icon-180.png": ("image/png", "public, max-age=604800"),
    "icon-192.png": ("image/png", "public, max-age=604800"),
    "icon-512.png": ("image/png", "public, max-age=604800"),
    "icon-maskable-512.png": ("image/png", "public, max-age=604800"),
    "manifest.webmanifest": ("application/manifest+json; charset=utf-8", "no-cache"),
    "sw.js": ("application/javascript; charset=utf-8", "no-cache"),
}

# 目录型静态资源：前缀 → webui/ 下的目录名。只放行下列后缀，源码目录里的
# .py / __pycache__ / *.map 等不会被暴露。
STATIC_PREFIXES: dict[str, tuple[str, str]] = {
    "/frontend/": ("frontend", "no-cache"),
    "/vendor/": ("vendor", "public, max-age=604800"),
}

STATIC_CONTENT_TYPES: dict[str, str] = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".webmanifest": "application/manifest+json; charset=utf-8",
}


def resolve_static_tree(path: str) -> tuple[Path, str, str] | None:
    """把 ``/frontend/…`` ``/vendor/…`` 映射到 webui/ 下的文件（含穿越防护）。"""
    for prefix, (directory, cache_control) in STATIC_PREFIXES.items():
        if not path.startswith(prefix):
            continue
        relative = path[len(prefix):]
        if not relative or relative.endswith("/"):
            return None
        root = (config.WEBUI_DIR / directory).resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return None  # 目录穿越
        content_type = STATIC_CONTENT_TYPES.get(candidate.suffix.lower())
        if content_type is None or not candidate.is_file():
            return None
        return candidate, content_type, cache_control
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "LiveStreamWebUI/2.0"

    def send_json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def authenticated(self) -> bool:
        # 认证已移除：本 WebUI 设计为仅在内网/隧道/受控反代后使用。
        # 如需恢复认证，在下方改为校验 X-Auth-Token 并设置 LIVE_WEBUI_TOKEN 环境变量。
        return True

    def send_file(self, path: Path, content_type: str, cache_control: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(body)

    def send_file_download(self, path: Path) -> None:
        """以附件方式下载录制文件，支持 HTTP Range（浏览器内视频拖动/续传）。"""
        try:
            size = path.stat().st_size
        except OSError:
            self.send_json(HTTPStatus.NOT_FOUND, {"error": "文件不存在"})
            return
        start, end, status = 0, size - 1, HTTPStatus.OK
        range_header = self.headers.get("Range", "")
        if range_header:
            match = re.match(r"bytes=(\d*)-(\d*)", range_header)
            if match:
                rs, re_part = match.groups()
                if rs:
                    start = int(rs)
                if re_part:
                    end = min(int(re_part), size - 1)
                if start > end or start >= size:
                    self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                status = HTTPStatus.PARTIAL_CONTENT
        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(length))
        self.send_header("Accept-Ranges", "bytes")
        if range_header:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Disposition", f'inline; filename="{quote(path.name)}"')
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command == "HEAD":
            return
        try:
            with path.open("rb") as fh:
                fh.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = fh.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # 客户端提前断开（如取消下载）

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                self.send_file(config.INDEX_FILE, "text/html; charset=utf-8", "no-store")
            elif parsed.path == "/index.html":
                # Direct hit on the file name (kept fresh; cache layer is the SW)
                self.send_file(config.INDEX_FILE, "text/html; charset=utf-8", "no-store")
            elif parsed.path.lstrip("/") in STATIC_FILES:
                name = parsed.path.lstrip("/")
                content_type, cache_control = STATIC_FILES[name]
                self.send_file(config.WEBUI_DIR / name, content_type, cache_control)
            elif (tree := resolve_static_tree(parsed.path)) is not None:
                file_path, content_type, cache_control = tree
                self.send_file(file_path, content_type, cache_control)
            elif parsed.path == "/api/jobs":
                self.send_json(HTTPStatus.OK, control.list_jobs())
            elif parsed.path == "/api/logs":
                query = parse_qs(parsed.query)
                unit = query.get("unit", [""])[0]
                tail = int(query.get("tail", ["200"])[0] or "200")
                self.send_json(HTTPStatus.OK, {"logs": control.job_logs(unit, tail)})
            elif parsed.path == "/api/files":
                query = parse_qs(parsed.query)
                q = query.get("q", [""])[0]
                limit = int(query.get("limit", ["300"])[0] or "300")
                offset = int(query.get("offset", ["0"])[0] or "0")
                self.send_json(HTTPStatus.OK, files.list_files(q, limit=limit, offset=offset))
            elif parsed.path == "/api/file":
                rel = parse_qs(parsed.query).get("path", [""])[0]
                path = files.resolve_recording(rel)
                if path is None:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "文件不存在"})
                    return
                self.send_file_download(path)
            elif parsed.path == "/api/overview":
                self.send_json(HTTPStatus.OK, stats.overview())
            elif parsed.path == "/api/health":
                self.send_json(HTTPStatus.OK, {"ok": True, "recorderd": control.health()})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except control.ControlUnavailable as exc:
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 16_384:
                raise ValueError("请求过大")
            data = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/start":
                self.send_json(HTTPStatus.CREATED, {"unit": control.start_job(data)})
            elif self.path == "/api/pause":
                control.pause_job(str(data.get("unit", "")))
                self.send_json(HTTPStatus.OK, {"ok": True})
            elif self.path == "/api/resume":
                self.send_json(HTTPStatus.OK, {"unit": control.resume_job(str(data.get("unit", "")))})
            elif self.path == "/api/restart":
                control.restart_job(str(data.get("unit", "")))
                self.send_json(HTTPStatus.OK, {"ok": True})
            elif self.path == "/api/delete-task":
                control.delete_job(str(data.get("unit", "")))
                self.send_json(HTTPStatus.OK, {"ok": True})
            elif self.path == "/api/delete":
                files.delete_file(str(data.get("path", "")))
                self.send_json(HTTPStatus.OK, {"ok": True})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except control.ControlUnavailable as exc:
            self.send_json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
        except (ValueError, RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    host = os.environ.get("LIVE_WEBUI_HOST", "127.0.0.1")
    port = int(os.environ.get("LIVE_WEBUI_PORT", "8765"))

    # 本进程不再托管录制引擎（见 ADR 0002）：SIGTERM 直接退出即可，
    # 不会打断任何录制；引擎由 livestream-recorderd.service 自己收尾。
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Live Stream WebUI: http://{host}:{port}", flush=True)
    print(f"录制控制面：{config.RECORDERD_SOCKET}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
