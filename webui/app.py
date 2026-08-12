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
from urllib.parse import parse_qs, urlparse


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_FILE = Path(__file__).resolve().parent / "index.html"
SYSTEMCTL = os.environ.get("SYSTEMCTL", "systemctl")
SYSTEMD_RUN = os.environ.get("SYSTEMD_RUN", "systemd-run")
AUTH_TOKEN = os.environ.get("LIVE_WEBUI_TOKEN", "")
RECORDINGS_DIR = os.environ.get("RECORDINGS_DIR", str(PROJECT_ROOT / "recordings"))

PLATFORMS = {
    "tiktok": ("tk/record.sh",),
    "douyin": ("douyin/record.sh",),
    "soop": ("soop/record.sh",),
    "kick": ("kick/record.sh",),
    "youtube": ("youtube/record.sh",),
    "chzzk": ("chzzk/record.sh",),
}


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=check, timeout=20)


def unit_name(platform: str, target: str) -> str:
    readable = re.sub(r"[^a-z0-9]+", "-", target.lower()).strip("-")[:24] or "channel"
    digest = hashlib.sha256(f"{platform}\0{target}".encode()).hexdigest()[:10]
    return f"livestream-rec-{platform}-{readable}-{digest}.service"


def list_jobs() -> list[dict[str, object]]:
    result = run(
        [SYSTEMCTL, "list-units", "livestream-rec-*.service", "--all", "--no-legend", "--plain"],
        check=False,
    )
    jobs = []
    for line in result.stdout.splitlines():
        fields = line.split(None, 4)
        if not fields:
            continue
        unit = fields[0]
        details = run(
            [SYSTEMCTL, "show", unit, "--property=Id,ActiveState,SubState,Description,ExecMainStartTimestamp,MainPID,MemoryCurrent,NRestarts"],
            check=False,
        )
        values = dict(item.split("=", 1) for item in details.stdout.splitlines() if "=" in item)
        description = values.get("Description", "")
        match = re.match(r"Live recorder: (\S+) (.+)", description)
        jobs.append(
            {
                "unit": values.get("Id", unit),
                "state": values.get("ActiveState", "unknown"),
                "substate": values.get("SubState", "unknown"),
                "description": description,
                "started": values.get("ExecMainStartTimestamp", ""),
                "platform": match.group(1) if match else "unknown",
                "target": match.group(2) if match else description,
                "pid": int(values.get("MainPID", "0") or 0),
                "memory": int(values.get("MemoryCurrent", "0") or 0),
                "restarts": int(values.get("NRestarts", "0") or 0),
            }
        )
    return jobs


def recent_files(limit: int = 12) -> list[dict[str, object]]:
    files: list[tuple[float, Path, int]] = []
    for path in PROJECT_ROOT.glob("**/*.mp4"):
        if ".git" not in path.parts and "DouyinLiveRecorder" not in path.parts:
            try:
                stat = path.stat()
                files.append((stat.st_mtime, path, stat.st_size))
            except FileNotFoundError:
                continue
    files.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            "name": path.name,
            "path": str(path.relative_to(PROJECT_ROOT)),
            "size": size,
            "modified": int(modified),
        }
        for modified, path, size in files[:limit]
    ]


def overview() -> dict[str, object]:
    usage = shutil.disk_usage(RECORDINGS_DIR if Path(RECORDINGS_DIR).exists() else PROJECT_ROOT)
    jobs = list_jobs()
    return {
        "jobs": len(jobs),
        "running": sum(job["state"] == "active" for job in jobs),
        "disk_total": usage.total,
        "disk_used": usage.used,
        "disk_free": usage.free,
        "disk_percent": round(usage.used / usage.total * 100, 1),
        "files": recent_files(),
        "server_time": int(time.time()),
    }


def start_job(data: dict) -> str:
    platform = str(data.get("platform", "")).lower()
    target = str(data.get("target", "")).strip()
    if platform not in PLATFORMS:
        raise ValueError("不支持的平台")
    if not target or len(target) > 500 or "\x00" in target:
        raise ValueError("频道或直播 URL 无效")

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
    result = run(
        [
            SYSTEMD_RUN,
            f"--unit={unit.removesuffix('.service')}",
            "--collect",
            "--service-type=exec",
            f"--description={description}",
            f"--working-directory={PROJECT_ROOT}",
            f"--setenv=RECORDINGS_DIR={RECORDINGS_DIR}",
            "--property=Restart=on-failure",
            "--property=RestartSec=10s",
            "--",
            *command,
        ],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip() or "systemd 启动失败")
    return unit


def stop_job(unit: str) -> None:
    if not re.fullmatch(r"livestream-rec-[a-z0-9-]+\.service", unit):
        raise ValueError("任务名称无效")
    result = run([SYSTEMCTL, "stop", unit], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "停止任务失败")


def job_logs(unit: str) -> str:
    if not re.fullmatch(r"livestream-rec-[a-z0-9-]+\.service", unit):
        raise ValueError("任务名称无效")
    result = run(["journalctl", "-u", unit, "-n", "200", "--no-pager", "-o", "short-iso"], check=False)
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
        return not AUTH_TOKEN or self.headers.get("X-Auth-Token", "") == AUTH_TOKEN

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                body = INDEX_FILE.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/api/jobs":
                if not self.authenticated():
                    self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "认证失败"})
                    return
                self.send_json(HTTPStatus.OK, list_jobs())
            elif parsed.path == "/api/logs":
                if not self.authenticated():
                    self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "认证失败"})
                    return
                unit = parse_qs(parsed.query).get("unit", [""])[0]
                self.send_json(HTTPStatus.OK, {"logs": job_logs(unit)})
            elif parsed.path == "/api/overview":
                if not self.authenticated():
                    self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "认证失败"})
                    return
                self.send_json(HTTPStatus.OK, overview())
            elif parsed.path == "/api/health":
                self.send_json(HTTPStatus.OK, {"ok": True})
            else:
                self.send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_POST(self) -> None:  # noqa: N802
        if not self.authenticated():
            self.send_json(HTTPStatus.UNAUTHORIZED, {"error": "认证失败"})
            return
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
