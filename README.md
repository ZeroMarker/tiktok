# Live Stream Toolkit

用于无人值守录制直播，或将直播源转推到 Bilibili。

## 支持范围

- TikTok：本地分段录制、转推 Bilibili
- 抖音：本地分段录制
- SOOP：本地分段录制、转推 Bilibili
- Twitch：转推 Bilibili
- YouTube：转推 Bilibili

## 快速开始

初始化依赖：

```bash
uv venv
uv tool install "yt-dlp[default,curl-cffi]"
git submodule update --init --recursive
```

检测命令：

```bash
yt-dlp --version
ffmpeg -version
python --version
```

录制 TikTok：

```bash
bash tk/record.sh <tiktok_username>
```

录制抖音：

```bash
bash douyin/record.sh <web_rid|抖音号|完整URL>
```

录制 SOOP：

```bash
bash soop/record.sh <soop_username|SOOP直播链接>
```

转推前先配置 Bilibili 推流地址，详见 [配置](docs/configuration.md)。

## 常用文档

- [项目结构](docs/structure.md)
- [配置](docs/configuration.md)
- [使用说明](docs/usage.md)
- [排障](docs/troubleshooting.md)
- [TikTok 直播录制使用与排障](docs/tiktok-live-recording.md)
- [B站视频上传接口文档](docs/bilibili-upload-api.md)

## 运行产物

录制脚本会按账号创建输出目录，并每 10 分钟生成一个 MP4 文件。日志默认写入对应 `logs/` 目录。

仓库已忽略日志、视频文件、Cookie 文件和 `recordings/`。建议长期任务在仓库外或 `recordings/` 下运行，避免运行产物和源码混在一起。
