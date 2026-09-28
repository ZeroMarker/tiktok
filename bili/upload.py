"""upload.py — Bilibili 稿件投稿（Web 端接口，标准库 only）。

把本地录制文件投成 B 站稿件，复用 ``live.py`` 扫码登录得到的会话
（``.bilibili_session.json``），不新增依赖。接口说明见
``docs/bilibili-upload-api.md``，流程：

    1. 预上传  GET  /preupload                 → endpoint / auth / biz_id / upos_uri
    2. 登记    POST {upos_url}?uploads          → upload_id
    3. 分片    PUT  {upos_url}?partNumber=...  → 每片 ETag
    4. 合并    POST {upos_url}?output=json
    5. 提交    POST /x/vu/web/add/v3            → aid / bvid

``push`` 只把文件传上 B 站存储并落一份 state JSON，**不建稿件**；
``post`` 读 state 提交稿件。中断后可用同一份 state 续投已传好的文件。

``--session`` / ``--state`` 是全局参数，须写在子命令之前。

登录态按账号分档存放（见 ``accounts.py``）：本工具默认用 ``upload`` 账号，
``live.py`` 默认用 ``live`` 账号，两者互不干扰；``--account NAME`` 可临时跨用。

用法：
    python3 upload.py accounts
    python3 upload.py use <账号名>                 # 改投稿的默认账号
    python3 upload.py --account NAME status        # 看某个账号的登录态
    python3 upload.py --state s.json push <文件|目录> [...] [--limit 3]
    python3 upload.py --state s.json post --title T --tid N [--tag a,b]
    python3 upload.py post <文件> [...] --title T --tid N

参数口径见 ``docs/bilibili-upload-api.md`` 第 5、7 节（自制/转载、风控、频率）。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import threading
import time
import urllib.parse
import urllib.request
from http.client import HTTPResponse
from pathlib import Path
from urllib.error import HTTPError

import accounts as bili_accounts
import live as bili_live
from live import BiliError, LEGACY_SESSION, extract_cookie_value, load_session, save_session

# 普通稿件的上传 profile。biliup 明确注释过：``ugcfx/bup`` 需要额外上传
# metadata 与 frame.zip，脚本化场景一律用 ``ugcupos/bup``。
PROFILE = "ugcupos/bup"
# 预上传线路参数（对应 member.bilibili.com/preupload?r=probe 返回的 query）。
LINE_QUERY = {"probe_version": "20221109", "upcdn": "txa", "zone": "cs"}
PREUPLOAD_URL = "https://member.bilibili.com/preupload"
SUBMIT_URL = "https://member.bilibili.com/x/vu/web/add/v3"
UPLOAD_PAGE = "https://member.bilibili.com/platform/upload/video/frame"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
)
TIMEOUT = 60
PART_TIMEOUT = 240
DEFAULT_CHUNK_SIZE = 10 * 1024 * 1024
# 单分片重试次数，取预上传返回的 chunk_retry（缺省 3）。
DEFAULT_PART_RETRY = 3
MAX_TITLE = 80

STATE_VERSION = 1
#: 本工具（稿件投稿）的默认账号名，与 live.py 的 ``live`` 分开。
TOOL = "upload"


def _now_ms() -> int:
    return int(time.time() * 1000)


def truncate_title(title: str, limit: int = MAX_TITLE) -> str:
    """按字符数截断到 B 站标题上限（不是字节数）。"""
    if len(title) <= limit:
        return title
    return title[: limit - 3] + "..."


def expand_inputs(inputs: list[str]) -> list[Path]:
    """把文件/目录参数展开为 mp4 列表：目录取其下 ``*.mp4`` 按文件名排序。"""
    files: list[Path] = []
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            files.extend(sorted(p for p in path.glob("*.mp4") if p.is_file()))
        elif path.is_file():
            files.append(path)
        else:
            raise BiliError(f"找不到输入：{raw}")
    if not files:
        raise BiliError("没有可上传的 mp4 文件")
    return files


def _http(
    url: str,
    *,
    method: str = "GET",
    cookies: str = "",
    data: bytes | None = None,
    headers: dict | None = None,
    timeout: int = TIMEOUT,
) -> tuple[int, dict, bytes]:
    """发一次 HTTP 请求，返回 ``(status, headers, body)``；非 2xx 不抛异常。"""
    hdrs = {
        "User-Agent": UA,
        "Referer": UPLOAD_PAGE,
        "Origin": "https://member.bilibili.com",
        "Accept": "*/*",
    }
    if cookies:
        hdrs["Cookie"] = cookies
    if headers:
        hdrs.update(headers)
    request = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310
            assert isinstance(resp, HTTPResponse)
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except HTTPError as exc:
        return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, exc.read()
    except OSError as exc:
        raise BiliError(f"网络错误：{exc}") from exc


def _json_call(
    url: str,
    *,
    method: str = "GET",
    cookies: str = "",
    payload: dict | None = None,
    headers: dict | None = None,
    timeout: int = TIMEOUT,
    allow_codes: tuple = (),
) -> dict:
    """发 JSON 请求并解析响应；``code != 0`` 抛 :class:`BiliError`。

    upos 的 ``OK`` 字段与 member 接口的 ``code`` 字段都归一到这里判定。
    """
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    hdrs = dict(headers or {})
    if body is not None:
        hdrs.setdefault("Content-Type", "application/json; charset=utf-8")
    status, _, raw = _http(url, method=method, cookies=cookies, data=body, headers=hdrs, timeout=timeout)
    text = raw.decode("utf-8", "replace")
    if status >= 400:
        raise BiliError(f"HTTP {status}：{text[-300:]}")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BiliError(f"JSON 解析失败：{text[-300:]}") from exc
    if not isinstance(parsed, dict):
        raise BiliError("接口返回异常（非 JSON 对象）")
    code = parsed.get("code", 0 if parsed.get("OK") == 1 else -1)
    if code != 0 and code not in allow_codes:
        raise BiliError(f"接口报错 [{code}]：{parsed.get('message') or text[-200:]}")
    return parsed


class Uploader:
    """封装一次投稿用到的全部 B 站接口。"""

    def __init__(self, cookies: str, csrf: str = ""):
        self.cookies = cookies
        self.csrf = csrf or extract_cookie_value(cookies, "bili_jct")

    # ---------- 阶段 1：预上传 ----------

    def preupload(self, name: str, size: int) -> dict:
        """预上传：拿上传节点、鉴权串、biz_id 与 upos 路径。"""
        params = {
            "name": name,
            "r": "upos",
            "profile": PROFILE,
            "ssl": "0",
            "version": "2.14.0",
            "build": "2140000",
            "size": str(size),
            **LINE_QUERY,
        }
        url = f"{PREUPLOAD_URL}?{urllib.parse.urlencode(params)}"
        return _json_call(url, cookies=self.cookies)

    # ---------- 阶段 2-4：文件直传 ----------

    def upload(self, path: Path, *, limit: int = 3, progress=None) -> dict:
        """把单个文件直传到 B 站存储，返回可提交稿件的文件凭证。"""
        try:
            size = path.stat().st_size
        except OSError as exc:
            raise BiliError(f"读取文件失败：{path}（{exc}）") from exc
        if size <= 0:
            raise BiliError(f"文件为空：{path}")

        bucket = self.preupload(path.name, size)
        auth = str(bucket.get("auth") or "")
        endpoint = str(bucket.get("endpoint") or "")
        upos_uri = str(bucket.get("upos_uri") or "")
        biz_id = bucket.get("biz_id")
        if not (auth and endpoint and upos_uri and biz_id is not None):
            raise BiliError(f"预上传返回缺字段：{json.dumps(bucket)[:300]}")
        # endpoint 形如 ``//upos-cs-upcdntxa.bilivideo.com``，自带协议相对前缀；
        # upos_uri 形如 ``upos://ugcever/xxx.mp4``，去掉协议头即上传路径。
        host = endpoint.strip().removeprefix("//").rstrip("/")
        base = f"https://{host}/{upos_uri.split('://', 1)[-1].lstrip('/')}"
        chunk_size = int(bucket.get("chunk_size") or DEFAULT_CHUNK_SIZE)
        retry = int(bucket.get("chunk_retry") or DEFAULT_PART_RETRY)

        upload_id = self._register(auth, base, size, chunk_size, biz_id)
        parts = self._put_parts(
            auth, base, upload_id, path, size, chunk_size, retry, limit, progress
        )
        self._merge(auth, base, upload_id, path.name, biz_id, parts)

        # 提交稿件的 filename 取 upos_uri 的无后缀文件名（biliup 同款口径）。
        return {
            "path": str(path),
            "size": size,
            "filename": Path(upos_uri).stem,
            "biz_id": biz_id,
        }

    def _register(self, auth: str, base: str, size: int, chunk_size: int, biz_id) -> str:
        params = {
            "uploads": "",
            "output": "json",
            "profile": PROFILE,
            "filesize": str(size),
            "partsize": str(chunk_size),
            "biz_id": str(biz_id),
        }
        payload = _json_call(
            f"{base}?{urllib.parse.urlencode(params)}",
            method="POST",
            cookies=self.cookies,
            headers={"X-Upos-Auth": auth},
        )
        upload_id = str(payload.get("upload_id") or "")
        if not upload_id:
            raise BiliError(f"登记上传失败：{json.dumps(payload)[:300]}")
        return upload_id

    def _put_parts(
        self,
        auth: str,
        base: str,
        upload_id: str,
        path: Path,
        size: int,
        chunk_size: int,
        retry: int,
        limit: int,
        progress,
    ) -> list[dict]:
        chunks = max(1, -(-size // chunk_size))
        sent = 0
        lock = threading.Lock()

        def send(index: int) -> dict:
            nonlocal sent
            start = index * chunk_size
            end = min(start + chunk_size, size)
            with path.open("rb") as handle:
                handle.seek(start)
                data = handle.read(end - start)
            if len(data) != end - start:
                raise BiliError(f"读取分片失败：{path} @{start}")
            params = {
                "partNumber": str(index + 1),
                "uploadId": upload_id,
                "chunk": str(index),
                "chunks": str(chunks),
                "size": str(len(data)),
                "start": str(start),
                "end": str(end),
                "total": str(size),
            }
            etag = ""
            last = ""
            for attempt in range(1, max(1, retry) + 1):
                try:
                    status, headers, body = _http(
                        f"{base}?{urllib.parse.urlencode(params)}",
                        method="PUT",
                        cookies=self.cookies,
                        data=data,
                        headers={"X-Upos-Auth": auth, "Content-Type": "application/octet-stream"},
                        timeout=PART_TIMEOUT,
                    )
                    if status < 400:
                        etag = (headers.get("etag") or "").strip().strip('"') or "etag"
                        break
                    last = f"HTTP {status}：{body[:200]!r}"
                except BiliError as exc:
                    last = str(exc)
                if attempt < max(1, retry):
                    time.sleep(min(2**attempt, 10))
            if not etag:
                raise BiliError(f"分片 {index + 1}/{chunks} 上传失败：{last}")
            with lock:
                sent += len(data)
                if progress is not None:
                    progress(sent, size)
            return {"partNumber": index + 1, "eTag": etag}

        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, limit)) as pool:
            # 结果按分片序号排列（B 站合并时要求 parts 连续有序）。
            return [future.result() for future in [pool.submit(send, i) for i in range(chunks)]]

    def _merge(self, auth: str, base: str, upload_id: str, name: str, biz_id, parts: list[dict]) -> None:
        params = {
            "output": "json",
            "name": name,
            "profile": PROFILE,
            "uploadId": upload_id,
            "biz_id": str(biz_id),
        }
        _json_call(
            f"{base}?{urllib.parse.urlencode(params)}",
            method="POST",
            cookies=self.cookies,
            payload={"parts": parts},
            headers={"X-Upos-Auth": auth},
        )

    # ---------- 阶段 5：提交稿件 ----------

    def submit(self, payload: dict) -> dict:
        """提交稿件，返回 ``{"aid": ..., "bvid": ...}``。"""
        if not self.csrf:
            raise BiliError("会话缺少 bili_jct，无法提交稿件")
        body = {**payload, "csrf": self.csrf}
        url = f"{SUBMIT_URL}?{urllib.parse.urlencode({'t': _now_ms(), 'csrf': self.csrf})}"
        result = _json_call(url, method="POST", cookies=self.cookies, payload=body)
        data = result.get("data") or {}
        return {"aid": data.get("aid"), "bvid": data.get("bvid")}


def build_payload(
    videos: list[dict],
    *,
    title: str,
    tid: int,
    tag: str = "",
    desc: str = "",
    dynamic: str = "",
    copyright: int = 1,
    source: str = "",
    tid_v2: int | None = None,
    only_self: bool = False,
    no_reprint: int = 1,
) -> dict:
    """组装 ``/x/vu/web/add/v3`` 的 JSON 正文。

    ``copyright=2``（转载）时必须带 ``source``，否则稿件会被打回。
    """
    if not videos:
        raise BiliError("没有可提交的视频文件")
    if copyright == 2 and not source.strip():
        raise BiliError("转载稿件必须提供 --source（原作者/来源）")
    payload = {
        "videos": [
            {
                "filename": item["filename"],
                "title": truncate_title(item.get("title") or title),
                "desc": item.get("desc", ""),
                "cid": item["biz_id"],
            }
            for item in videos
        ],
        "cover": "",
        "cover43": "",
        "title": truncate_title(title),
        "copyright": copyright,
        "tid": tid,
        "tag": tag,
        "desc_format_id": 9999,
        "desc": desc,
        "recreate": -1,
        "dynamic": dynamic,
        "interactive": 0,
        "act_reserve_create": 0,
        "no_disturbance": 0,
        "no_reprint": no_reprint,
        "subtitle": {"open": 0, "lan": ""},
        "dolby": 0,
        "lossless_music": 0,
        "up_selection_reply": False,
        "up_close_reply": False,
        "up_close_danmu": False,
        "web_os": 3,
    }
    if copyright == 2:
        payload["source"] = source
    if tid_v2 is not None:
        payload["human_type2"] = tid_v2
    if only_self:
        payload["is_only_self"] = 1
    return payload


# ---------- state（断点续投） ----------


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"version": STATE_VERSION, "videos": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BiliError(f"state 文件损坏：{path}（{exc}）") from exc
    if not isinstance(data, dict) or not isinstance(data.get("videos"), list):
        raise BiliError(f"state 文件格式错误：{path}")
    return data


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["version"] = STATE_VERSION
    state["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


# ---------- CLI ----------


def _account_name(args: argparse.Namespace) -> str:
    return args.account or bili_accounts.tool_default_account(TOOL)


def _session(args: argparse.Namespace) -> tuple[Uploader, dict]:
    session = load_session(args.session)
    cookies = session.get("cookies", "")
    name = _account_name(args)
    if not cookies:
        raise BiliError(
            f"账号 {name} 未登录：请先执行 `python3 live.py login --account {name}`"
            f"（可用 `python3 live.py accounts` 看已登录的账号）"
        )
    return Uploader(cookies, session.get("csrf_token", "")), session


def _human_size(num: int) -> str:
    if num < 1024 * 1024:
        return f"{num / 1024:.0f} KB"
    return f"{num / 1024 / 1024:.1f} MB"


def _make_progress(label: str):
    lock = threading.Lock()
    state = {"last": 0.0}

    def report(sent: int, total: int) -> None:
        now = time.time()
        with lock:
            if now - state["last"] < 1.0 and sent < total:
                return
            state["last"] = now
        line = f"  {label} {sent * 100 // max(1, total):3d}%（{_human_size(sent)}/{_human_size(total)}）"
        sys.stderr.write(f"\r{line}\033[K" if sent < total else f"{line}\n")
        sys.stderr.flush()

    return report


def _push_files(uploader: Uploader, files: list[Path], args) -> list[dict]:
    state = load_state(args.state)
    known = {item["path"]: item for item in state["videos"] if item.get("path") and item.get("biz_id")}
    videos: list[dict] = []
    for index, path in enumerate(files, start=1):
        cached = known.get(str(path))
        if cached and not args.reupload and Path(cached["path"]).is_file():
            print(f"[{index}/{len(files)}] 已上传，跳过：{path.name}", flush=True)
            videos.append(cached)
            continue
        size = path.stat().st_size
        print(f"[{index}/{len(files)}] 上传 {path.name}（{_human_size(size)}）", flush=True)
        record = uploader.upload(path, limit=args.limit, progress=_make_progress(path.name))
        print(f"    完成：filename={record['filename']} cid={record['biz_id']}", flush=True)
        videos.append(record)
        save_state(args.state, {"version": STATE_VERSION, "videos": videos})
    save_state(args.state, {"version": STATE_VERSION, "videos": videos})
    return videos


def _apply_part_titles(videos: list[dict], prefix: str | None) -> list[dict]:
    """给每个分 P 生成 ``<prefix> NN`` 标题；未给 prefix 时沿用稿件标题。"""
    if not prefix:
        return videos
    out = []
    for index, item in enumerate(videos, start=1):
        out.append({**item, "title": truncate_title(f"{prefix} {index:02d}")})
    return out


def cmd_status(args: argparse.Namespace) -> int:
    from live import check_login

    session = load_session(args.session)
    cookies = session.get("cookies", "")
    name = _account_name(args)
    if not cookies:
        if not args.session.exists():
            print(f"账号 {name} 尚未登录：请先执行 `python3 live.py login --account {name}`")
        else:
            print(f"账号 {name} 的会话文件没有 Cookie（{args.session}），请重新登录")
        return 1
    ok, mid = check_login(cookies)
    print(f"登录状态：{'已登录' if ok else '未登录'} 账号={name}", end="")
    if ok:
        print(f" mid={mid}", end="")
    expiry = bili_accounts.session_expiry(session)
    if expiry:
        print(f" SESSDATA 到期={expiry:%Y-%m-%d}", end="")
    print()
    return 0 if ok else 1


def cmd_accounts(args: argparse.Namespace) -> int:
    return bili_live.cmd_accounts(args)


def cmd_use(args: argparse.Namespace) -> int:
    target = bili_accounts.set_tool_default_account(TOOL, args.name)
    print(f"upload.py（稿件投稿）默认账号已切到 {args.name}（{target}）")
    return 0


def cmd_push(args: argparse.Namespace) -> int:
    uploader, _ = _session(args)
    files = expand_inputs(args.inputs)
    videos = _push_files(uploader, files, args)
    print(f"已上传 {len(videos)} 个文件，凭证写入 {args.state}")
    print("执行 `post --state ...` 提交稿件（此刻账号里还没有新稿件）")
    return 0


def cmd_post(args: argparse.Namespace) -> int:
    uploader, _ = _session(args)
    if args.inputs:
        files = expand_inputs(args.inputs)
        videos = _push_files(uploader, files, args)
    else:
        videos = load_state(args.state)["videos"]
        if not videos:
            raise BiliError(f"state 里没有已上传文件：{args.state}")
    videos = _apply_part_titles(videos, args.part_title_prefix)
    payload = build_payload(
        videos,
        title=args.title,
        tid=args.tid,
        tag=args.tag,
        desc=args.desc,
        dynamic=args.dynamic,
        copyright=args.copyright,
        source=args.source,
        tid_v2=args.tid_v2,
        only_self=args.only_self,
    )
    print(f"提交稿件：{args.title}（{len(videos)} 个分 P，分区 {args.tid}）")
    result = uploader.submit(payload)
    print(f"投稿成功：av={result['aid']} bv={result['bvid']}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="upload.py", description="Bilibili 稿件投稿（Web 端接口）")
    parser.add_argument("--session", type=Path, default=None, help="会话文件路径（覆盖账号选择）")
    parser.add_argument("--account", default=None, help=f"使用哪个账号（默认：{TOOL}）")
    parser.add_argument("--state", type=Path, default=Path("upload-state.json"), help="上传凭证 state 文件")
    sub = parser.add_subparsers(dest="cmd", required=True)

    accounts = sub.add_parser("accounts", help="列出所有账号与登录态有效期")
    accounts.set_defaults(func=cmd_accounts)

    use = sub.add_parser("use", help="把本工具的默认账号切到指定账号")
    use.add_argument("name", help="账号名")
    use.set_defaults(func=cmd_use)

    status = sub.add_parser("status", help="检查登录状态")
    status.set_defaults(func=cmd_status)

    push = sub.add_parser("push", help="只上传文件，不建稿件")
    push.add_argument("inputs", nargs="+", help="mp4 文件或目录")
    push.add_argument("--limit", type=int, default=3, help="单文件分片并发数")
    push.add_argument("--reupload", action="store_true", help="忽略 state 缓存，强制重传")
    push.set_defaults(func=cmd_push)

    post = sub.add_parser("post", help="提交稿件（可先传文件，也可只读 state）")
    post.add_argument("inputs", nargs="*", help="mp4 文件或目录；省略则只读 state")
    post.add_argument("--title", required=True, help="稿件标题")
    post.add_argument("--tid", type=int, required=True, help="分区 ID")
    post.add_argument("--tid-v2", type=int, default=None, help="新分区 ID（human_type2，可选）")
    post.add_argument("--tag", default="", help="标签，逗号分隔")
    post.add_argument("--desc", default="", help="简介")
    post.add_argument("--dynamic", default="", help="空间动态文案")
    post.add_argument("--copyright", type=int, default=2, choices=(1, 2), help="1 自制 / 2 转载（默认 2）")
    post.add_argument("--source", default="", help="转载来源（copyright=2 时必填）")
    post.add_argument("--part-title-prefix", default="", help="分 P 标题前缀，形如「场次名」，自动追加序号")
    post.add_argument("--only-self", action="store_true", help="先设为仅自己可见，审核前自查用")
    post.add_argument("--limit", type=int, default=3, help="单文件分片并发数")
    post.add_argument("--reupload", action="store_true", help="忽略 state 缓存，强制重传")
    post.set_defaults(func=cmd_post)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        # 与 live.py 共用同一套账号档案；此处只做自身默认账号的解析（迁移交给 live.py）
        args.session = bili_accounts.resolve_session(args.session, args.account, TOOL, LEGACY_SESSION)
        return args.func(args)
    except bili_accounts.AccountError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except BiliError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已取消（已上传的凭证保留在 state 里，可继续）", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
