"""字幕管线的有界队列与输出进度看门狗（无模型依赖）。"""
import queue
import time


def offer_latest(items, item):
    try:
        items.put_nowait(item)
    except queue.Full:
        try:
            items.get_nowait()
        except queue.Empty:
            pass
        items.put_nowait(item)


def output_time(path):
    try:
        with path.open("rb") as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 65536))
            lines = stream.read().splitlines()
        for line in reversed(lines):
            if line.startswith(b"out_time_us="):
                return int(line.split(b"=", 1)[1])
    except (OSError, ValueError):
        pass
    return None


def watch_pipeline(puller, pusher, progress, stop, failed, log, timeout=60, interval=5):
    latest, changed = None, time.monotonic()
    while not stop.wait(interval):
        code = pusher.poll()
        if code == 0 and puller.poll() is not None:
            return
        if code is not None:
            log("字幕编码推流进程已退出，结束本轮并等待重试")
            failed.set()
            puller.terminate()
            return
        current = output_time(progress)
        if current is not None and (latest is None or current > latest):
            latest, changed = current, time.monotonic()
        if time.monotonic() - changed >= timeout:
            log(f"字幕推流 {timeout} 秒无输出进度，结束本轮并等待重试")
            failed.set()
            puller.terminate()
            pusher.terminate()
            return
