"""dlr.py — 多平台无人值守直播录制引擎入口。

统一所有平台的录制行为（检测、输出布局、ffmpeg 分段、优雅停止、断流重试），
每平台仅提供解析适配器（见 dlr/adapters/）。

用法：
    python3 scripts/dlr.py <platform> <target> [选项]

平台：
    youtube kick chzzk soop tiktok douyin

选项：
    --cookies FILE       Netscape 格式 Cookie 文件（抖音等需要登录的平台）
    --cookie HEADER      原始 Cookie 请求头
    --recordings-dir DIR 录制输出根目录（默认 $RECORDINGS_DIR 或 ./recordings）
    --segment-seconds N  每段 MP4 时长（默认 600）
    --detect-interval N  未开播时的重试间隔（默认 60）
    --break-seconds N    断流后重新抓取间隔（默认 10）
    --quality 原画/1080p/720p/480p（默认 best 原画）
"""

from __future__ import annotations

import argparse
import sys

from dlr.engine import Engine

PLATFORMS = ("youtube", "kick", "chzzk", "soop", "tiktok", "douyin")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dlr",
        description="多平台无人值守直播录制引擎",
    )
    parser.add_argument("platform", choices=PLATFORMS, help="平台")
    parser.add_argument("target", help="频道/直播间标识或直播 URL")
    parser.add_argument("--cookies", metavar="FILE", help="Netscape 格式 Cookie 文件")
    parser.add_argument("--cookie", metavar="HEADER", help="原始 Cookie 请求头")
    parser.add_argument("--recordings-dir", default=None, help="录制输出根目录")
    parser.add_argument("--segment-seconds", type=int, default=600, help="每段 MP4 时长（秒）")
    parser.add_argument("--detect-interval", type=int, default=60, help="未开播重试间隔（秒）")
    parser.add_argument("--break-seconds", type=int, default=10, help="断流后重试间隔（秒）")
    parser.add_argument(
        "--quality",
        choices=("best", "1080p", "720p", "480p"),
        default="best",
        help="录制画质上限（best 为原画档）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    engine = Engine.from_args(args)
    return engine.run()


if __name__ == "__main__":
    sys.exit(main())
