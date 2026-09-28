"""accounts.py — Bilibili 多账号登录态档案。

一份登录态一个文件，默认落在 ``~/.config/bili/accounts/<账号名>.json``（目录 700、
文件 600），与既有的 ``push.env`` / ``live.env`` 同居。每个工具各有一个默认账号名，
记录在同目录 ``defaults.json``：``live.py`` 默认 ``live``（开播/推流），
``upload.py`` 默认 ``upload``（稿件投稿）。

本模块被 ``live.py``、``upload.py`` 和 ``webui/app.py`` 共用，避免三处各写一遍
解析逻辑。会话的实际内容与扫码流程仍由 ``live.py`` 负责，这里只管**存哪、选谁**。
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

CONFIG_DIR = Path.home() / ".config" / "bili"
ACCOUNTS_DIR = CONFIG_DIR / "accounts"
DEFAULTS_FILE_NAME = "defaults.json"
DEFAULT_ACCOUNT = "live"
#: 各工具的内置默认账号名。用户没跑过 ``use`` 时按这张表取，
#: 跑过则以 ``defaults.json`` 里的显式选择为准。
TOOL_DEFAULTS = {"live": "live", "upload": "upload"}
#: 账号名白名单：留出 `.json` 后缀，且不允许 `..` 之类的路径穿越。
_NAME_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


class AccountError(RuntimeError):
    """账号档案相关的错误（由调用方包装成对外提示）。"""


def accounts_dir() -> Path:
    """账号档案目录。测试可用 ``BILI_ACCOUNTS_DIR`` 覆盖。"""
    override = os.environ.get("BILI_ACCOUNTS_DIR")
    return Path(override) if override else ACCOUNTS_DIR


def validate_account_name(name: str) -> str:
    if not _NAME_RE.fullmatch(name or ""):
        raise AccountError(f"账号名不合法（只允许字母、数字、下划线、连字符，1-64 字符）：{name!r}")
    return name


def account_path(name: str) -> Path:
    return accounts_dir() / f"{validate_account_name(name)}.json"


# ---------- 每个工具的默认账号 ----------


def read_defaults() -> dict:
    path = accounts_dir() / DEFAULTS_FILE_NAME
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}  # 损坏时退回内置默认，不阻断开播/投稿
    return data if isinstance(data, dict) else {}


def write_defaults(data: dict) -> None:
    path = accounts_dir() / DEFAULTS_FILE_NAME
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def tool_default_account(tool: str) -> str:
    """该工具在未显式指定 ``--account`` 时使用的账号。

    显式设置（``defaults.json``）优先；否则按内置表取 ``live`` / ``upload``，
    未知工具才退到 :data:`DEFAULT_ACCOUNT`。
    """
    return str(read_defaults().get(tool) or TOOL_DEFAULTS.get(tool) or DEFAULT_ACCOUNT)


def set_tool_default_account(tool: str, name: str) -> Path:
    """把某工具的默认账号改成 ``name``；目标必须已登录过。"""
    target = account_path(name)
    if not target.exists():
        raise AccountError(f"账号 {name} 尚未登录：先执行 `python3 live.py login --account {name}`")
    data = read_defaults()
    data[tool] = name
    write_defaults(data)
    return target


# ---------- 解析 ----------


def resolve_session(explicit: Path | None, account: str | None, tool: str, legacy: Path) -> Path:
    """把 ``--session`` / ``--account`` / 工具默认值收敛成一个会话文件路径。

    优先级：``--session`` 显式路径 > ``--account`` 账号 > 该工具的默认账号；
    默认账号档案不存在但老会话文件还在时，回落到老文件（迁移前的过渡态）。
    """
    if explicit is not None:
        return explicit
    name = validate_account_name(account) if account else tool_default_account(tool)
    path = account_path(name)
    if path.exists() or not legacy.exists():
        return path
    return legacy


# ---------- 展示与体检 ----------


def _cookie_value(cookies: str, key: str) -> str:
    """从 ``a=1; b=2`` 串里取单个值。刻意不 import live.py：本模块被 live.py 依赖。"""
    for part in cookies.split(";"):
        part = part.strip()
        if part.startswith(key + "="):
            return part[len(key) + 1 :]
    return ""


def session_expiry(session: dict) -> datetime | None:
    """从 SESSDATA 的第二段解析过期时间；格式对不上返回 None。"""
    raw = _cookie_value(str(session.get("cookies") or ""), "SESSDATA")
    parts = unquote(raw).split(",")
    if len(parts) < 2:
        return None
    try:
        return datetime.fromtimestamp(int(parts[1]))
    except (ValueError, OSError, OverflowError):
        return None


def read_session(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def list_accounts() -> list[dict]:
    """列出所有已登录账号（含登录态字段），供 ``accounts`` 子命令展示。"""
    directory = accounts_dir()
    if not directory.is_dir():
        return []
    out = []
    for path in sorted(directory.glob("*.json")):
        if path.name == DEFAULTS_FILE_NAME:
            continue
        session = read_session(path)
        expires = session_expiry(session)
        out.append(
            {
                "name": path.stem,
                "path": path,
                "mid": str(session.get("mid") or ""),
                "room_id": str(session.get("room_id") or ""),
                "title": str(session.get("title") or ""),
                "has_push_code": bool(session.get("rtmp_code")),
                "expires": expires,
                "expired": bool(expires and expires.timestamp() < time.time()),
            }
        )
    return out


def migrate_legacy(legacy: Path, target_name: str = DEFAULT_ACCOUNT) -> str | None:
    """把老的单账号会话文件迁到 ``accounts/<target_name>.json``。

    仅在「老文件存在且目标档案不存在」时执行一次；原文件改名保留为 ``.bak``。
    返回给用户看的一行提示，没发生迁移则返回 None。
    """
    target = account_path(target_name)
    if not legacy.exists() or target.exists():
        return None
    session = read_session(legacy)
    if not session.get("cookies"):
        return None
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(target)
    backup = legacy.with_suffix(legacy.suffix + ".bak")
    legacy.replace(backup)
    return f"已迁移登录态：{legacy.name} → {target}（原文件备份为 {backup.name}）"
