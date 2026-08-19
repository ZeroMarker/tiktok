"""抖音适配器：复用 douyin/get_stream.py（基于 DouyinLiveRecorder 子模块）。

get_stream.py 负责解析直播源与昵称；适配器只做转发与兜底重试。
"""

from __future__ import annotations

from dlr.adapters.base import BaseAdapter, PROJECT_ROOT, extract_last_segment

GET_STREAM_PY = PROJECT_ROOT / "douyin" / "get_stream.py"


class DouyinAdapter(BaseAdapter):
    platform = "douyin"
    referer = "https://www.douyin.com/"
    bsf_aac = True

    def _extract_identifier(self) -> str:
        return extract_last_segment(self.target)

    def detect_stream_url(self) -> str | None:
        if not GET_STREAM_PY.is_file():
            return None
        cmd = ["python3", str(GET_STREAM_PY), self.target, "--get-url"] + self.cookie_args()
        return self.run_capture(cmd)

    def get_nickname(self) -> str | None:
        if not GET_STREAM_PY.is_file():
            return None
        cmd = ["python3", str(GET_STREAM_PY), self.target, "--get-nickname"] + self.cookie_args()
        return self.run_capture(cmd)
