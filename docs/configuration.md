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

脚本启动时会检查对应依赖；缺少命令时会直接退出并给出错误，而不会进入无限重试。

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

如果任一变量为空，转推脚本会在启动 ffmpeg 前退出。脚本不会在终端输出完整推流地址、推流码或直播源签名 URL。

## 抖音子模块

抖音录制依赖 `douyin/DouyinLiveRecorder`：

```bash
git submodule update --init --recursive
```

如果 Python 无法导入依赖，先确认该目录存在并且子模块已拉取完成。
抖音录制入口也会在启动时检查子模块，并提示上述初始化命令。

## 抖音 Cookie

Cookie 文件使用 Netscape 格式。可以用项目脚本从本机已登录的浏览器导出：

```bash
bash douyin/import_cookies.sh chrome ./douyin-cookies.txt
```

导出文件会自动设置为仅当前用户可读写，并已被 `.gitignore` 排除。不要提交、分享或写入日志。
