#!/usr/bin/env python3
"""Local Web UI for managing livestream recorder systemd units."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEBUI_DIR = Path(__file__).resolve().parent
INDEX_FILE = WEBUI_DIR / "index.html"
SYSTEMCTL = os.environ.get("SYSTEMCTL", "systemctl")
SYSTEMD_RUN = os.environ.get("SYSTEMD_RUN", "systemd-run")
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", str(PROJECT_ROOT / "recordings"))
# 录制进程运行的非 root 身份。留空则仍以 root 运行（不推荐）。
# 设置后，systemd-run 生成的各频道单元将以该用户运行，需确保其可写输出目录/日志目录。
RECORDER_USER = os.environ.get("RECORDER_USER", "").strip()

PLATFORMS = {
    "tiktok": ("tk/record.sh",),
    "douyin": ("douyin/record.sh",),
    "soop": ("soop/record.sh",),
    "kick": ("kick/record.sh",),
    "youtube": ("youtube/record.sh",),
    "chzzk": ("chzzk/record.sh",),
}

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


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check, timeout=20)


def unit_name(platform: str, target: str) -> str:
    readable = re.sub(r"[^a-z0-9]+", "-", target.lower()).strip("-")[:24] or "channel"
    digest = hashlib.sha256(f"{platform}\0{target}".encode()).hexdigest()[:10]
    return f"livestream-rec-{platform}-{readable}-{digest}.service"


def _parse_int(value: object, default: int = 0) -> int:
    """Parse optional numeric systemd properties without breaking the API."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def list_jobs() -> list[dict[str, object]]:
    result = run(
        [SYSTEMCTL, "list-units", "livestream-rec-*.service", "--all", "--no-legend", "--plain"],
        check=False,
    )
    units = [line.split(None, 1)[0] for line in result.stdout.splitlines() if line.strip()]
    if not units:
        return []
    details = run(
        [SYSTEMCTL, "show", *units, "--property=Id,ActiveState,SubState,Description,ExecMainStartTimestamp,MainPID,MemoryCurrent,NRestarts"],
        check=False,
    )
    jobs = []
    for block in details.stdout.strip().split("\n\n"):
        values = dict(item.split("=", 1) for item in block.splitlines() if "=" in item)
        if not values.get("Id"):
            continue
        description = values.get("Description", "")
        match = re.match(r"Live recorder: (\S+) (.+)", description)
        jobs.append(
            {
                "unit": values["Id"],
                "state": values.get("ActiveState", "unknown"),
                "substate": values.get("SubState", "unknown"),
                "description": description,
                "started": values.get("ExecMainStartTimestamp", ""),
                "platform": match.group(1) if match else "unknown",
                "target": match.group(2) if match else description,
                "pid": _parse_int(values.get("MainPID")),
                "memory": _parse_int(values.get("MemoryCurrent")),
                "restarts": _parse_int(values.get("NRestarts")),
            }
        )
    return jobs


def list_files(query: str = "", limit: int = 300, offset: int = 0) -> dict[str, object]:
    """列出 RECORDINGS_DIR 下的录制文件（按修改时间倒序，支持搜索与分页）。"""
    recordings_root = Path(RECORDINGS_DIR).expanduser().resolve()
    if not recordings_root.is_dir():
        return {"total": 0, "offset": offset, "files": []}
    q = query.strip().lower()
    files: list[tuple[float, Path, int]] = []
    for path in recordings_root.glob("**/*.mp4"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if q:
            rel = path.relative_to(recordings_root).as_posix().lower()
            if q not in path.name.lower() and q not in rel:
                continue
        files.append((stat.st_mtime, path, stat.st_size))
    files.sort(key=lambda item: item[0], reverse=True)
    total = len(files)
    page = files[offset : offset + limit]
    return {
        "total": total,
        "offset": offset,
        "files": [
            {
                "name": path.name,
                "path": str(path.relative_to(recordings_root)),
                "dir": str(path.parent.relative_to(recordings_root)) if path.parent != recordings_root else "",
                "size": size,
                "modified": int(modified),
            }
            for modified, path, size in page
        ],
    }


def recent_files(limit: int = 12) -> list[dict[str, object]]:
    return list_files(limit=limit)["files"]


def resolve_recording(rel: str) -> Path | None:
    """将相对路径安全解析到 RECORDINGS_DIR 内的文件，越界返回 None。"""
    if not rel or "\x00" in rel:
        return None
    root = Path(RECORDINGS_DIR).expanduser().resolve()
    path = (root / rel).resolve()
    if path == root or not str(path).startswith(str(root) + os.sep):
        return None
    return path if path.is_file() else None


def delete_file(rel: str) -> None:
    path = resolve_recording(rel)
    if path is None:
        raise ValueError("文件路径无效或文件不存在")
    try:
        path.unlink()
    except OSError as exc:
        raise RuntimeError(f"删除失败: {exc}")


def system_stats() -> dict[str, object]:
    """系统负载与内存概览（尽力而为，读取失败返回空值）。"""
    try:
        load1, load5, load15 = os.getloadavg()
        load = [round(load1, 2), round(load5, 2), round(load15, 2)]
    except (OSError, AttributeError):
        load = []
    mem_total = mem_available = 0
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                key, _, value = line.partition(":")
                if key == "MemTotal":
                    mem_total = int(value.strip().split()[0]) * 1024
                elif key == "MemAvailable":
                    mem_available = int(value.strip().split()[0]) * 1024
    except OSError:
        pass
    return {"load": load, "mem_total": mem_total, "mem_available": mem_available}


def overview() -> dict[str, object]:
    usage = shutil.disk_usage(RECORDINGS_DIR if Path(RECORDINGS_DIR).exists() else PROJECT_ROOT)
    jobs = list_jobs()
    platforms: dict[str, int] = {}
    for job in jobs:
        platforms[job["platform"]] = platforms.get(job["platform"], 0) + 1
    stats = system_stats()
    return {
        "jobs": len(jobs),
        "running": sum(job["state"] == "active" for job in jobs),
        "failed": sum(job["state"] == "failed" for job in jobs),
        "platforms": platforms,
        "disk_total": usage.total,
        "disk_used": usage.used,
        "disk_free": usage.free,
        "disk_percent": round(usage.used / usage.total * 100, 1),
        "files": recent_files(),
        "load": stats["load"],
        "mem_total": stats["mem_total"],
        "mem_available": stats["mem_available"],
        "server_time": int(time.time()),
    }


def start_job(data: dict) -> str:
    platform = str(data.get("platform", "")).lower()
    target = str(data.get("target", "")).strip()
    if platform not in PLATFORMS:
        raise ValueError("不支持的平台")
    if not target or len(target) > 500 or "\x00" in target:
        raise ValueError("频道或直播 URL 无效")
    # 校验重复：同一平台下相同频道（忽略大小写）不允许重复添加
    normalized = target.casefold()
    for job in list_jobs():
        if job.get("platform") == platform and str(job.get("target", "")).strip().casefold() == normalized:
            raise ValueError(f"录制任务已存在：{platform} {job.get('target')}，请勿重复添加，如需重跑请直接重启该任务")

    script = PROJECT_ROOT / PLATFORMS[platform][0]
    command = ["bash", str(script), target]
    cookie_file = str(data.get("cookie_file", "")).strip()
    if platform == "douyin" and cookie_file:
        cookie_path = Path(cookie_file).expanduser().resolve()
        if not cookie_path.is_file():
            raise ValueError("Cookie 文件不存在")
        command.extend(["--cookies", str(cookie_path)])

    unit = unit_name(platform, target)
    description = f"Live recorder: {platform} {target}"[:200]
    argv = [
        SYSTEMD_RUN,
        f"--unit={unit.removesuffix('.service')}",
        "--collect",
        "--service-type=exec",
        f"--description={description}",
        f"--working-directory={PROJECT_ROOT}",
        f"--setenv=RECORDINGS_DIR={RECORDINGS_DIR}",
        # 网络依赖：等网络就绪后再拉起录制
        "--property=After=network-online.target",
        "--property=Wants=network-online.target",
        # 停止语义：先 SIGTERM 主进程（脚本 trap 干净收尾 ffmpeg），超时后 SIGKILL 整个 cgroup
        "--property=KillMode=mixed",
        "--property=TimeoutStopSec=30s",
        # 重启策略
        "--property=Restart=on-failure",
        "--property=RestartSec=10s",
    ]
    # 以非 root 身份运行录制（RECORDER_USER 设置时）
    if RECORDER_USER:
        argv += [f"--uid={RECORDER_USER}", f"--gid={RECORDER_USER}"]
    argv += ["--", *command]
    result = run(argv, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "systemd 启动失败")
    return unit


def _valid_unit(unit: str) -> bool:
    return bool(re.fullmatch(r"livestream-rec-[a-z0-9-]+\.service", unit))


def stop_job(unit: str) -> None:
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    result = run([SYSTEMCTL, "stop", unit], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "停止任务失败")


def restart_job(unit: str) -> None:
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    result = run([SYSTEMCTL, "restart", unit], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "重启任务失败")


def job_logs(unit: str, tail: int = 200) -> str:
    if not _valid_unit(unit):
        raise ValueError("任务名称无效")
    tail = max(1, min(int(tail), 5000))
    result = run(["journalctl", "-u", unit, "-n", str(tail), "--no-pager", "-o", "short-iso"], check=False)
    return result.stdout[-100_000:]


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
        self.send_header("Content-Disposition", f'attachment; filename="{quote(path.name)}"')
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
                self.send_file(INDEX_FILE, "text/html; charset=utf-8", "no-store")
            elif parsed.path == "/index.html":
                # Direct hit on the file name (kept fresh; cache layer is the SW)
                self.send_file(INDEX_FILE, "text/html; charset=utf-8", "no-store")
            elif parsed.path.lstrip("/") in STATIC_FILES:
                name = parsed.path.lstrip("/")
                content_type, cache_control = STATIC_FILES[name]
                self.send_file(WEBUI_DIR / name, content_type, cache_control)
            elif parsed.path == "/api/jobs":
                self.send_json(HTTPStatus.OK, list_jobs())
            elif parsed.path == "/api/logs":
                query = parse_qs(parsed.query)
                unit = query.get("unit", [""])[0]
                tail = int(query.get("tail", ["200"])[0] or "200")
                self.send_json(HTTPStatus.OK, {"logs": job_logs(unit, tail)})
            elif parsed.path == "/api/files":
                query = parse_qs(parsed.query)
                q = query.get("q", [""])[0]
                limit = int(query.get("limit", ["300"])[0] or "300")
                offset = int(query.get("offset", ["0"])[0] or "0")
                self.send_json(HTTPStatus.OK, list_files(q, limit=limit, offset=offset))
            elif parsed.path == "/api/file":
                rel = parse_qs(parsed.query).get("path", [""])[0]
                path = resolve_recording(rel)
                if path is None:
                    self.send_json(HTTPStatus.NOT_FOUND, {"error": "文件不存在"})
                    return
                self.send_file_download(path)
            elif parsed.path == "/api/overview":
                self.send_json(HTTPStatus.OK, overview())
            elif parsed.path == "/api/health":
                self.send_json(HTTPStatus.OK, {"ok": True})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 16_384:
                raise ValueError("请求过大")
            data = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/start":
                self.send_json(HTTPStatus.CREATED, {"unit": start_job(data)})
            elif self.path == "/api/stop":
                stop_job(str(data.get("unit", "")))
                self.send_json(HTTPStatus.OK, {"ok": True})
            elif self.path == "/api/restart":
                restart_job(str(data.get("unit", "")))
                self.send_json(HTTPStatus.OK, {"ok": True})
            elif self.path == "/api/delete":
                delete_file(str(data.get("path", "")))
                self.send_json(HTTPStatus.OK, {"ok": True})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, RuntimeError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"{self.address_string()} - {fmt % args}")


def main() -> None:
    host = os.environ.get("LIVE_WEBUI_HOST", "127.0.0.1")
    port = int(os.environ.get("LIVE_WEBUI_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Live Stream WebUI: http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
