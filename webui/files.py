"""录制文件列表、解析与删除（RECORDINGS_DIR 扫描）。"""

from __future__ import annotations

import os
from pathlib import Path

from webui import config


def list_files(query: str = "", limit: int = 300, offset: int = 0) -> dict[str, object]:
    """列出 RECORDINGS_DIR 下的录制文件（按修改时间倒序，支持搜索与分页）。"""
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    recordings_root = Path(config.RECORDINGS_DIR).expanduser().resolve()
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
    root = Path(config.RECORDINGS_DIR).expanduser().resolve()
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
