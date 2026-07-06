# 配置

## 基础依赖

需要以下命令可用：

- Bash 或 PowerShell
- Python 3
- `ffmpeg`
- `yt-dlp`
- `uv`

推荐初始化：

```bash
uv venv
uv tool install "yt-dlp[default,curl-cffi]"
```

确认依赖：

```bash
yt-dlp --version
ffmpeg -version
python --version
```

直播源抓取失败时，优先更新 `yt-dlp`：

```bash
yt-dlp --update-to nightly
```

## Bilibili 推流

转推脚本从 `~/.bashrc` 读取 Bilibili 推流地址和密钥：

```bash
export BILIBILI_PUSH_URL="rtmp://example/live-bvc/"
export BILIBILI_PUSH_CODE="your-stream-key"
```

修改后重新加载：

```bash
source ~/.bashrc
```

推流脚本会拼接：

```text
${BILIBILI_PUSH_URL}${BILIBILI_PUSH_CODE}
```

## 抖音子模块

抖音录制依赖 `douyin/DouyinLiveRecorder`：

```bash
git submodule update --init --recursive
```

如果 Python 无法导入依赖，先确认该目录存在并且子模块已拉取完成。
