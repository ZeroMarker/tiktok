#!/usr/bin/env python3
"""值守守护进程（bili-monitord.service）：固定目标开播自动起推流、关播自动停推流。

目标只认 live.env 的 TARGET（管理页填一次即固定）；值守开关是 auto.env 的 AUTO
（「停止全部推流」/「停播」会关掉，避免把用户明确停掉的东西拉回来）。

每 60 秒一轮，收到 SIGUSR1 立即跑一轮（管理页「立即检测」）。每轮结果写进
~/.config/bili/monitord.json —— 本进程是它唯一的写入者，管理页只读。
与管理页的用户操作经 pushctl.control_lock() 互斥：用户在操作时本轮让路。

独立成服务是为了让值守的生命周期与管理页无关：重启/杀掉管理页不影响值守。
"""

from __future__ import annotations

import signal
import threading
import time

import pushctl as ctl

POLL_INTERVAL = 60.0
# 连续未开播到第几次才停推流：单次失败可能是网络抖动或 WAF 拦，误停会让停播延迟
OFFLINE_STREAK_TO_STOP = 2

# 进程内状态；每次 record 落盘。streak / close_pending 启动时从快照恢复，
# 重启 monitord 不会丢掉「已经连续下播 1 次」「关播失败待重试」。
state: dict[str, object] = {
    "target": "",          # 当前固定目标（每轮从 live.env 重读，改目标立即生效）
    "live": None,          # True 开播 / False 未开播 / None 未知
    "detail": "等待首次检测",
    "source": "",          # push=ffmpeg 在推（不额外探测）/ probe=探测结果
    "checked_at": 0.0,     # 上次检测完成的墙钟时间
    "next_at": 0.0,        # 下次检测的墙钟时间
    "streak": 0,           # 连续未开播次数
    "epoch": "",           # 上次见到的值守纪元（auto.env EPOCH），变化即清零 streak
    "close_pending": False,  # 已停推流但关播失败，下轮重试
}


def load_state() -> None:
    saved = ctl.read_monitor_state() or {}
    for key in ("target", "streak", "epoch", "close_pending"):
        if key in saved:
            state[key] = saved[key]


def record(live: bool | None, detail: str, source: str, streak: int | None = None) -> None:
    now = time.time()
    state.update(live=live, detail=detail, source=source, checked_at=now, next_at=now + POLL_INTERVAL)
    if streak is not None:
        state["streak"] = streak
    ctl.write_monitor_state(state)


def auto_control(action) -> bool:
    """执行自动接管动作：拿不到控制锁（用户正在操作）就让路，本轮跳过、下轮再来。"""
    try:
        with ctl.control_lock():
            action()
        return True
    except ctl.ControlBusy:
        return False
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"值守自动接管失败：{exc}", flush=True)
        return False


def start_live_unit(target: str) -> None:
    """开播自动起推流：先保证房间在播，再拉起直播推流单元（同管理页切直播的路径）。"""
    ctl.ensure_room_live()
    ctl.write_env(ctl.LIVE_ENV, [f"TARGET={target}"])
    ctl.restart_unit(ctl.LIVE_UNIT)


def recover_live_unit() -> None:
    """脚本仍在重试时也检查房间；重新开播换码后重启以加载新码。"""
    if ctl.ensure_room_live():
        ctl.ctl("restart", ctl.LIVE_UNIT)
        record(True, "B 站房间已重新开播，推流已重启", "probe", 0)


def stop_offline_live() -> None:
    """停止转推并关播；关播失败时保留待处理标记，下轮重试，值守保持开启。"""
    state["close_pending"] = True
    ctl.write_monitor_state(state)
    ctl.ctl("disable", "--now", ctl.LIVE_UNIT)
    if not ctl.wait_inactive(ctl.LIVE_UNIT):
        raise RuntimeError("直播推流尚未停止，稍后重试关播")
    ctl.close_room()
    state["close_pending"] = False
    record(False, "主播下播 → 已停止推流并关闭 B 站直播间，值守继续", "probe")


def cycle() -> None:
    """一轮监测：读固定目标 → 判断在播 → 必要时自动启停推流。可独立测试。"""
    target = ctl.read_env(ctl.LIVE_ENV, "TARGET").strip()
    epoch = ctl.arm_epoch()
    # 换人 / 重新开值守都清零连续失败计数：旧的账不该带进新一轮
    if state["target"] != target or state["epoch"] != epoch:
        state["streak"] = 0
    state["target"], state["epoch"] = target, epoch
    if not ctl.TARGET_RE.fullmatch(target or ""):
        record(None, "未设置目标主播（管理页填一次即固定）", "")
        return

    units = ctl.show_many(ctl.LIVE_UNIT, ctl.REPLAY_UNIT)
    live, replay = units[ctl.LIVE_UNIT], units[ctl.REPLAY_UNIT]
    if replay["active"] == "active":
        # 两种模式互斥是硬约束：轮播单元在跑时不抢，只报状态。
        # 判 active 而不是判 ffmpeg：轮播卡死（ffmpeg 已退）时抢单元会变成双推流。
        record(None, "文件轮播运行中，暂不接管", "")
        return
    if live["active"] == "active" and ctl.pushing([live["pid"]]).get(live["pid"], False):
        # ffmpeg 有流在推就等于开播，不必再打一次 TikTok
        record(True, "推流中（ffmpeg 已连上源）", "push", 0)
        return

    stream, detail = ctl.probe_target(target)
    armed = ctl.auto_armed()
    if stream:
        record(True, detail, "probe", 0)
        if live["active"] != "active" and armed:
            if auto_control(lambda: start_live_unit(target)):
                record(True, "开播 → 已自动起推流", "probe", 0)
        elif live["active"] == "active" and armed:
            auto_control(recover_live_unit)
        return

    streak = int(state["streak"]) + 1
    record(False, detail, "probe", streak)
    # 关播自动停推流：单次失败可能是网络抖动，连续两次才动手。
    if (streak >= OFFLINE_STREAK_TO_STOP and armed
            and (live["active"] == "active" or state["close_pending"])):
        auto_control(stop_offline_live)


def loop(stop: threading.Event, wake: threading.Event) -> None:
    while not stop.is_set():
        try:
            cycle()
        except Exception as exc:  # noqa: BLE001 — 守护进程不能因未知异常退出
            record(None, f"检测异常：{exc}", "")
        wake.wait(POLL_INTERVAL)
        wake.clear()


def main() -> None:
    stop, wake = threading.Event(), threading.Event()

    def on_term(*_):
        stop.set()
        wake.set()

    signal.signal(signal.SIGTERM, on_term)
    signal.signal(signal.SIGINT, on_term)
    signal.signal(signal.SIGUSR1, lambda *_: wake.set())
    load_state()
    print("bili-monitord 启动：每 %ds 检测一次，SIGUSR1 立即检测" % POLL_INTERVAL, flush=True)
    loop(stop, wake)


if __name__ == "__main__":
    main()
