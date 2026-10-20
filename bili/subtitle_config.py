"""字幕运行依赖与私有凭据文件；可供控制面使用，无模型依赖。"""
import importlib.util
import os
import shlex
from pathlib import Path

CREDENTIAL_NAMES = ("ALIBABA_CLOUD_ACCESS_KEY_ID", "ALIBABA_CLOUD_ACCESS_KEY_SECRET")


def credential_file():
    return Path.home() / ".config/bili/aliyun.env"


def read_credentials(path=None):
    values = {}
    try:
        for line in (path or credential_file()).read_text().splitlines():
            line = line.strip().removeprefix("export ")
            if "=" not in line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            if key in CREDENTIAL_NAMES:
                parts = shlex.split(value, comments=True)
                if len(parts) == 1:
                    values[key] = parts[0]
    except (OSError, ValueError):
        return {}
    return values


def dependency_error():
    home = Path(os.environ.get("TUBE_ASR_HOME", Path.home() / ".local/share/tube-asr"))
    required = {
        "Nemotron 语音识别模型": home / "models/nemotron-3.5-asr-streaming-0.6b-Q8_0.gguf",
        "语音识别共享库": Path(os.environ.get("TRANSCRIBE_LIBRARY", home / "transcribe.cpp/build-shared/src/libtranscribe.so")),
        "语音识别 Python 绑定": home / "transcribe.cpp/bindings/python/src/transcribe_cpp/__init__.py",
        "字幕字体": Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    }
    for label, path in required.items():
        if not path.is_file():
            return f"缺少{label}"
    ffmpeg = Path(os.environ.get("BILI_FFMPEG", Path.home() / ".local/opt/ffmpeg/bin/ffmpeg"))
    if not ffmpeg.is_file() or not os.access(ffmpeg, os.X_OK):
        return "缺少支持字幕的 FFmpeg"
    if importlib.util.find_spec("numpy") is None:
        return "缺少 numpy"
    return ""
