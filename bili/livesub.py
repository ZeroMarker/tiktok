#!/usr/bin/env python3
"""实验：TikTok 直播转推时实时烧录日→中字幕。

一个 ffmpeg 取流：输出 1 叠加 drawtext 后推 RTMP（或写本地文件），输出 2 把音频以
16 kHz 单声道 f32 管道交给本进程。本进程用 Nemotron 3.5 流式 ASR（transcribe.cpp
Python 绑定，常驻模型）切句，送本地 llama-server 上的 Hy-MT2 翻译，再原子替换
drawtext 的 textfile（reload=1 每帧重读）。

字幕相对画面有约 1～3 秒滞后（ASR 提交 + 翻译耗时），画面不做延迟补偿。

依赖（均在仓库外，见 ~/tube/docs/nemotron-asr-linux.md、hy-mt2-test.md）：
- transcribe.cpp 共享库构建 build-shared/（TRANSCRIBE_BUILD_SHARED=ON）
- llama-server 已在 --mt-url 监听，加载 Hy-MT2

用法：
  python3 livesub.py marumo_rea --out /tmp/test.flv --duration 90
  python3 livesub.py marumo_rea --out rtmp     # 推 push.env 里的 B 站地址
"""
import argparse
import json
import os
import queue
import subprocess
import sys
import textwrap
import threading
import time
import urllib.request
from pathlib import Path

import numpy as np

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
        self._write()

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


def translate(url, text):
    body = {"messages": [{"role": "user", "content": MT_PROMPT + text}],
            "temperature": 0.7, "top_p": 0.6, "top_k": 20,
            "repeat_penalty": 1.05, "max_tokens": 128}
    req = urllib.request.Request(url, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["choices"][0]["message"]["content"].strip().replace("\n", " ")


def mt_worker(q, overlay, url, transcript):
    while True:
        ja = q.get()
        if ja is None:
            return
        t = time.time()
        try:
            zh = translate(url, ja)
        except Exception as e:  # noqa: BLE001 翻译失败只跳过这一句
            log("翻译失败:", e)
            continue
        log(f"MT {time.time() - t:.1f}s | {ja} => {zh}")
        transcript.write(f"{time.strftime('%H:%M:%S')}\t{ja}\t{zh}\n")
        transcript.flush()
        overlay.set(zh=zh)


def asr_loop(pipe, overlay, mtq, threads, language):
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
        while True:
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
                    mtq.put(seg)
            overlay.set(ja=full[sent:].lstrip("、。 "))
            overlay.expire()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("username")
    ap.add_argument("--out", required=True, help="本地文件路径，或 rtmp（用 push.env）")
    ap.add_argument("--duration", type=float, help="只跑这么多秒")
    ap.add_argument("--language", default="ja-JP")
    ap.add_argument("--asr-threads", type=int, default=2)
    ap.add_argument("--mt-url", default="http://127.0.0.1:18091/v1/chat/completions")
    ap.add_argument("--workdir", default="/tmp/livesub")
    args = ap.parse_args()

    work = Path(args.workdir)
    work.mkdir(parents=True, exist_ok=True)
    overlay = Overlay(work / "sub.txt")
    transcript = open(work / f"transcript_{args.username}_{time.strftime('%Y%m%d_%H%M%S')}.tsv",
                      "a", encoding="utf-8")

    here = Path(__file__).resolve().parent
    env = dict(os.environ, TIKTOK_HEVC_FLV="1")
    url = subprocess.run([sys.executable, str(here / "get_stream.py"), args.username],
                         capture_output=True, text=True, env=env).stdout.strip().splitlines()
    if not url:
        sys.exit(f"@{args.username} 未开播或取流失败")
    url = url[0]
    log("取流成功")

    ffmpeg = str(Path.home() / ".local/opt/ffmpeg/bin/ffmpeg")
    target = bili_rtmp() if args.out == "rtmp" else args.out
    draw = (f"drawtext=fontfile={FONT}:textfile={overlay.path}:reload=1:"
            "fontsize=34:fontcolor=white:line_spacing=8:borderw=2:bordercolor=black@0.8:"
            "box=1:boxcolor=black@0.35:boxborderw=10:"
            "x=(w-text_w)/2:y=h-text_h-120")
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "warning", "-re",
           "-headers", f"User-Agent: {UA}\r\nReferer: https://www.tiktok.com/\r\n",
           "-fflags", "+discardcorrupt", "-rw_timeout", "15000000",
           "-analyzeduration", "5M", "-probesize", "5M",
           "-reconnect", "1", "-reconnect_at_eof", "1", "-reconnect_streamed", "1",
           "-reconnect_on_network_error", "1", "-reconnect_delay_max", "5",
           *(["-t", str(args.duration)] if args.duration else []),
           "-i", url]
    # 输出 1：推流（参数同 push.sh v6，另加字幕）
    cmd += ["-map", "0:v:0", "-map", "0:a:0",
            "-vf", f"fps=25,scale='min(720,iw)':-2:flags=lanczos,{draw}",
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-b:v", "2500k", "-maxrate", "3000k", "-bufsize", "5000k",
            "-g", "50", "-keyint_min", "25", "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
            "-af", "aresample=async=1:first_pts=0",
            "-f", "flv", "-flvflags", "no_duration_filesize",
            "-max_muxing_queue_size", "9999", target]
    # 输出 2：ASR 音频
    cmd += ["-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "pipe:1"]

    mtq = queue.Queue()
    threading.Thread(target=mt_worker, args=(mtq, overlay, args.mt_url, transcript),
                     daemon=True).start()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    log("ffmpeg 已启动 ->", "B 站 RTMP" if args.out == "rtmp" else target)
    try:
        asr_loop(proc.stdout, overlay, mtq, args.asr_threads, args.language)
    except KeyboardInterrupt:
        pass
    finally:
        proc.terminate()
        proc.wait()
        mtq.put(None)
    log("结束，ffmpeg 退出码", proc.returncode)


if __name__ == "__main__":
    main()
