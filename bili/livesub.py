#!/usr/bin/env python3
"""TikTok 直播转推时实时烧录日→中字幕。

WebUI 可开关字幕；push.sh 在开启时调用本脚本，详见 docs/livesub.md。

一个 ffmpeg 取流：输出 1 叠加 drawtext 后推 RTMP（或写本地文件），输出 2 把音频以
16 kHz 单声道 f32 管道交给本进程。本进程用 Nemotron 3.5 流式 ASR（transcribe.cpp
Python 绑定，常驻模型）切句，送本地 Hy-MT2 或阿里云机器翻译，再原子替换
drawtext 的 textfile（reload=1 每帧重读）。

画面延迟：取流 ffmpeg 把音视频原样（-c copy）以 MPEG-TS 写进管道，本进程按到达时间
缓冲 --delay 秒再喂给编码推流的第二个 ffmpeg；ASR 音频不延迟。字幕更新也按「出现
时刻 + delay」排期，于是日文行与画面同步，中文行在该句说完、译好后出现。

本地翻译带上文（最近一句原文，Hy-MT2「背景信息」模板）和术语表（livesub-glossary.tsv，
命中的条目按官方「参考下面的翻译」模板注入）。ASR 不支持热词，术语表只作用于翻译。

依赖（均在仓库外，见 ~/tube/docs/nemotron-asr-linux.md、hy-mt2-test.md）：
- transcribe.cpp 共享库构建 build-shared/（TRANSCRIBE_BUILD_SHARED=ON）
- 本地翻译：llama-server 已在 --mt-url 监听，加载 Hy-MT2
- 云端翻译：--mt-backend aliyun，需设置 ALIBABA_CLOUD_ACCESS_KEY_ID
  和 ALIBABA_CLOUD_ACCESS_KEY_SECRET

用法：
  python3 livesub.py marumo_rea --out /tmp/test.flv --duration 90
  python3 livesub.py marumo_rea --out rtmp     # 推 push.env 里的 B 站地址
"""
import argparse
import heapq
import json
import os
import queue
import re
import signal
import subprocess
import sys
import textwrap
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np

import aliyun_mt
from subtitle_runtime import offer_latest, watch_pipeline

ASR_HOME = Path(os.environ.get("TUBE_ASR_HOME", Path.home() / ".local/share/tube-asr"))
ASR_MODEL = ASR_HOME / "models/nemotron-3.5-asr-streaming-0.6b-Q8_0.gguf"
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36")
SR = 16000
FEED = SR * 560 // 1000          # 每次喂 560 ms
PUNCT = "、。？！?!"
MIN_CHARS = 10                   # 标点处断句的最短长度
MAX_CHARS = 28                   # 超长强制断句
TAIL_GUARD = 3                   # 末尾几个字可能被改写，不参与断句
IDLE_FLUSH_S = 1.5               # 识别文本这么久没变化（且够长）就断句
IDLE_FORCE_S = 3.5               # 不论长短，这么久没变化就断句
CLEAR_AFTER_S = 6.0              # 字幕无更新这么久后清屏
WRAP = 18                        # 每行字数（720 宽、字号 34）
MT_PROMPT = "将以下文本翻译为中文，注意只需要输出翻译后的结果，不要额外解释：\n\n"
MT_CONTEXT = 1                   # 带几句上文（多了更慢，也更容易把上文一起译出）
GLOSSARY = Path(__file__).resolve().parent / "livesub-glossary.tsv"


def log(*a):
    print(time.strftime("[%H:%M:%S]"), *a, file=sys.stderr, flush=True)


def bili_rtmp():
    env = {}
    p = Path.home() / ".config/bili/push.env"
    for line in p.read_text().splitlines():
        line = line.strip().removeprefix("export ")
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v.strip().strip("'\"")
    return env["BILIBILI_PUSH_URL"] + env["BILIBILI_PUSH_CODE"]


class Overlay:
    """drawtext 的 textfile：上行日文（实时），下行中文（最近一句译文）。"""

    def __init__(self, path):
        self.path = Path(path)
        self.ja = ""
        self.zh = ""
        self.stamp = time.time()
        self.lock = threading.Lock()
        self.due = []
        self.seq = iter(range(1 << 62))
        self._write()
        threading.Thread(target=self.run, daemon=True).start()

    def set(self, ja=None, zh=None):
        with self.lock:
            if (ja is None or ja == self.ja) and (zh is None or zh == self.zh):
                return
            if ja is not None:
                self.ja = ja
            if zh is not None:
                self.zh = zh
            self.stamp = time.time()
            self._write()

    def set_at(self, when, **kw):
        """到 when（time.time()）时再 set，用于对齐延迟后的画面。"""
        with self.lock:
            heapq.heappush(self.due, (when, next(self.seq), kw))

    def run(self):
        while True:
            now = time.time()
            ready = []
            with self.lock:
                while self.due and self.due[0][0] <= now:
                    ready.append(heapq.heappop(self.due)[2])
            for kw in ready:
                self.set(**kw)
            self.expire()
            time.sleep(0.05)

    def expire(self):
        with self.lock:
            if (self.ja or self.zh) and time.time() - self.stamp > CLEAR_AFTER_S:
                self.ja = self.zh = ""
                self._write()

    def _write(self):
        lines = textwrap.wrap(self.ja, WRAP) + textwrap.wrap(self.zh, WRAP)
        tmp = self.path.with_suffix(".tmp")
        # drawtext 不接受空文件，留一个空格
        tmp.write_text("\n".join(lines[-4:]) or " ", encoding="utf-8")
        os.replace(tmp, self.path)


def load_glossary(path=GLOSSARY):
    """每行「原文[|别写…]<TAB>译文」，# 开头为注释。返回 [(别写元组, 原文, 译文)]。"""
    terms = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "\t" in line:
                src, dst = line.split("\t", 1)
                forms = tuple(f for f in src.split("|") if f)
                terms.append((forms, forms[0], dst.strip()))
    return terms


def build_prompt(text, context, terms):
    hits = [(f, dst) for forms, _, dst in terms for f in forms if f in text]
    head = ""
    if hits:
        head = "参考下面的翻译：\n" + "".join(f"{a} 翻译成 {b}\n" for a, b in hits) + "\n"
    if not context or len(text) < 5:  # 太短的片段带上文时模型会回显模板标签
        return head + MT_PROMPT + text
    return (f"{head}【背景信息】\n{''.join(context)}\n\n"
            "请结合背景信息将以下文本翻译为中文，注意只需要输出翻译后的结果，不要额外解释。\n\n"
            f"【待翻译文本】\n{text}")


def translate(url, text, context=(), terms=()):
    body = {"messages": [{"role": "user", "content": build_prompt(text, context, terms)}],
            "temperature": 0.7, "top_p": 0.6, "top_k": 20,
            "repeat_penalty": 1.05, "max_tokens": 128}
    req = urllib.request.Request(url, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        zh = json.load(r)["choices"][0]["message"]["content"].replace("\n", " ")
    zh = re.sub(r"【(待翻译文本|背景信息)】", "", zh).strip()
    # 带上文时模型偶尔把上文也译出来，译文明显过长就去掉上文重译
    if context and len(zh) > 1.6 * len(text) + 6:
        return translate(url, text, (), terms)
    return zh


def mt_worker(q, overlay, url, transcript, delay, backend="local"):
    terms = load_glossary() if backend == "local" else []
    log(f"翻译后端 {backend}" + (f"，术语表 {len(terms)} 条" if backend == "local" else ""))
    context = []
    while True:
        item = q.get()
        if item is None:
            return
        ja, cut_at = item
        if len(ja) <= 2:  # 「は」「かな」之类的碎片不值得占一条字幕
            continue
        t = time.time()
        try:
            zh = (aliyun_mt.translate(ja) if backend == "aliyun"
                  else translate(url, ja, context[-MT_CONTEXT:], terms))
        except Exception as e:  # noqa: BLE001 翻译失败只跳过这一句
            log("翻译失败:", e)
            continue
        log(f"MT {time.time() - t:.1f}s | {ja} => {zh}")
        if time.time() > cut_at + delay:
            log(f"字幕晚于排期 {time.time() - cut_at - delay:.1f}s")
        transcript.write(f"{time.strftime('%H:%M:%S')}\t{ja}\t{zh}\n")
        transcript.flush()
        context[:] = (context + [ja + "。"])[-MT_CONTEXT:]
        overlay.set_at(cut_at + delay, zh=zh)


def asr_loop(pipe, overlay, mtq, threads, language, delay, stop_requested=None):
    sys.path.insert(0, str(ASR_HOME / "transcribe.cpp/bindings/python/src"))
    os.environ.setdefault("TRANSCRIBE_LIBRARY",
                          str(ASR_HOME / "transcribe.cpp/build-shared/src/libtranscribe.so"))
    import transcribe_cpp as tc

    model = tc.Model(str(ASR_MODEL), backend="cpu")
    log("ASR 模型已加载")
    nbytes = FEED * 4
    with model.session(n_threads=threads) as session, \
            session.stream(language=language) as stream:
        # 该模型只在停顿处提交，连续说话时全部停留在 tentative（基本只追加），
        # 所以对 committed + tentative 全文自行切句：sent 为已送翻译的字数。
        sent = 0
        full = ""
        last_change = time.time()
        last_ja = ""
        while stop_requested is None or not stop_requested.is_set():
            buf = pipe.read(nbytes)
            if not buf:
                break
            pcm = np.frombuffer(buf[: len(buf) // 4 * 4], dtype=np.float32)
            upd = stream.feed(pcm)
            now = time.time()
            if upd.committed_changed or upd.tentative_changed:
                t = stream.text()
                full = t.committed + t.tentative
                last_change = now
                endpoint = not t.tentative
            else:
                endpoint = False
            sent = min(sent, len(full))  # 假设被改短
            pending = full[sent:]
            cut = 0
            idle = now - last_change
            if (len(pending.strip("、。 ")) >= MIN_CHARS and (endpoint or idle > IDLE_FLUSH_S)) \
                    or idle > IDLE_FORCE_S:
                cut = len(pending)
            else:
                stable = pending[:-TAIL_GUARD]
                for i in range(len(stable) - 1, MIN_CHARS - 2, -1):
                    if stable[i] in PUNCT:
                        cut = i + 1
                        break
                if not cut and len(stable) >= MAX_CHARS:
                    cut = MAX_CHARS
            if cut:
                seg = pending[:cut].strip("、。 ")
                sent += cut
                if seg:
                    offer_latest(mtq, (seg, now))
            ja = full[sent:].lstrip("、。 ")
            if ja != last_ja:
                overlay.set_at(now + delay, ja=ja)
                last_ja = ja


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("username")
    ap.add_argument("--out", required=True, help="本地文件路径，或 rtmp（用 push.env）")
    ap.add_argument("--source", help="跳过取流，直接用这个 URL 或本地文件（测试用）")
    ap.add_argument("--duration", type=float, help="只跑这么多秒")
    ap.add_argument("--language", default="ja-JP")
    ap.add_argument("--delay", type=float, default=5.0,
                    help="画面缓冲延迟秒数（默认 5 秒；识别或翻译较慢时需调大）")
    ap.add_argument("--asr-threads", type=int, default=2)
    ap.add_argument("--mt-url", default="http://127.0.0.1:18091/v1/chat/completions")
    ap.add_argument("--mt-backend", choices=("local", "aliyun"), default="local",
                    help="翻译后端（默认 local；aliyun 使用环境变量中的 AccessKey）")
    ap.add_argument("--workdir", default="/tmp/livesub")
    args = ap.parse_args()
    if args.mt_backend == "aliyun":
        aliyun_mt.credentials()
        if args.language != "ja-JP":
            ap.error("aliyun 后端当前仅支持 ja-JP → zh")
    if args.delay < 0 or not np.isfinite(args.delay):
        ap.error("delay 必须是有限的非负数")

    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    overlay = Overlay(work / "sub.txt")
    transcript = open(work / f"transcript_{args.username}_{time.strftime('%Y%m%d_%H%M%S')}.tsv",
                      "a", encoding="utf-8")

    here = Path(__file__).resolve().parent
    env = dict(os.environ, TIKTOK_HEVC_FLV="1")
    if args.source:
        url = [args.source]
    else:
        url = subprocess.run([sys.executable, str(here / "get_stream.py"), args.username],
                             capture_output=True, text=True, env=env).stdout.strip().splitlines()
    if not url:
        sys.exit(f"@{args.username} 未开播或取流失败")
    url = url[0]
    log("取流成功")

    ffmpeg = os.environ.get("BILI_FFMPEG", str(Path.home() / ".local/opt/ffmpeg/bin/ffmpeg"))
    target = bili_rtmp() if args.out == "rtmp" else args.out
    draw = (f"drawtext=fontfile={FONT}:textfile={overlay.path}:reload=1:"
            "fontsize=34:fontcolor=white:line_spacing=8:borderw=2:bordercolor=black@0.8:"
            "box=1:boxcolor=black@0.35:boxborderw=10:"
            "x=(w-text_w)/2:y=120")
    # 取流：输出 1 原样转 MPEG-TS 进管道（待延迟），输出 2 为 ASR 音频
    ts_r, ts_w = os.pipe()
    net = ["-headers", f"User-Agent: {UA}\r\nReferer: https://www.tiktok.com/\r\n",
           "-rw_timeout", "15000000",
           "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1",
           "-reconnect_on_network_error", "1", "-reconnect_delay_max", "5"]
    pull = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning", "-re",
            *(net if "://" in url else []),
            "-fflags", "+discardcorrupt", "-analyzeduration", "5M", "-probesize", "5M",
            *(["-t", str(args.duration)] if args.duration else []),
            "-i", url,
            "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-f", "mpegts", f"pipe:{ts_w}",
            "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"]
    # 推流：参数同 push.sh v6，另加字幕
    progress = work / "push-progress.log"
    progress.write_text("")
    push = [ffmpeg, "-y", "-nostdin", "-hide_banner", "-loglevel", "warning",
            "-stats_period", "10",
            "-progress", str(progress),
            "-fflags", "+discardcorrupt", "-analyzeduration", "5M", "-probesize", "5M",
            "-f", "mpegts", "-i", "pipe:0",
            "-map", "0:v:0", "-map", "0:a:0",
            "-vf", f"fps=25,scale='min(720,iw)':-2:flags=lanczos,{draw}",
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-b:v", "2500k", "-maxrate", "3000k", "-bufsize", "5000k",
            "-g", "50", "-keyint_min", "25", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-af", "aresample=async=1:first_pts=0",
            "-f", "flv", "-flvflags", "no_duration_filesize",
            "-max_muxing_queue_size", "9999", target]

    mtq = queue.Queue(maxsize=8)
    threading.Thread(target=mt_worker, args=(mtq, overlay, args.mt_url, transcript, args.delay,
                                           args.mt_backend),
                     daemon=True).start()
    pusher = subprocess.Popen(push, stdin=subprocess.PIPE)
    puller = subprocess.Popen(pull, stdout=subprocess.PIPE, pass_fds=(ts_w,))
    os.close(ts_w)
    threading.Thread(target=delay_pipe, args=(ts_r, pusher.stdin, args.delay),
                     daemon=True).start()
    stop, failed = threading.Event(), threading.Event()
    threading.Thread(target=watch_pipeline,
                     args=(puller, pusher, progress, stop, failed, log), daemon=True).start()
    log(f"ffmpeg 已启动，画面延迟 {args.delay}s ->", "B 站 RTMP" if args.out == "rtmp" else target)
    interrupted = False
    stop_requested = threading.Event()
    try:
        def on_term(*_):
            nonlocal interrupted
            interrupted = True
            stop_requested.set()
            # 不跨 ctypes 回调抛异常；停止音频生产者以唤醒 pipe.read。
            puller.terminate()
        signal.signal(signal.SIGTERM, on_term)
        signal.signal(signal.SIGINT, on_term)
        asr_loop(puller.stdout, overlay, mtq, args.asr_threads, args.language, args.delay,
                 stop_requested)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        stop.set()
        puller.terminate()
        try:
            puller.wait(timeout=5)
        except subprocess.TimeoutExpired:
            puller.kill()
            puller.wait()
        offer_latest(mtq, None)
        try:
            pusher.wait(args.delay + 15)  # 让缓冲里的画面推完
        except subprocess.TimeoutExpired:
            pusher.terminate()
            try:
                pusher.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pusher.kill()
                pusher.wait()
    log("结束，ffmpeg 退出码 取流", puller.returncode, "推流", pusher.returncode)
    if not interrupted and (failed.is_set() or puller.returncode not in (0, -15) or pusher.returncode != 0):
        sys.exit(1)


def delay_pipe(src_fd, dst, delay):
    """把 src_fd 读到的字节按到达时间延后 delay 秒写入 dst；src 结束后关闭 dst。"""
    buf = queue.Queue()

    def reader():
        with os.fdopen(src_fd, "rb", buffering=0) as f:
            while chunk := f.read(65536):
                buf.put((time.time() + delay, chunk))
        buf.put((0, None))

    threading.Thread(target=reader, daemon=True).start()
    try:
        while True:
            due, chunk = buf.get()
            if chunk is None:
                break
            if (wait := due - time.time()) > 0:
                time.sleep(wait)
            dst.write(chunk)
            dst.flush()
    except BrokenPipeError:
        log("推流 ffmpeg 已退出")
    finally:
        try:
            dst.close()
        except BrokenPipeError:
            pass


if __name__ == "__main__":
    main()
