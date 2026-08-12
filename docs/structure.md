# 项目结构

本项目按平台和用途组织脚本，根目录只保留项目入口、说明和跨平台脚本。

```text
.
├── bili/                 # 转推 Bilibili 的平台脚本
│   ├── push.sh           # TikTok -> Bilibili
│   └── soop.sh           # SOOP -> Bilibili
├── docs/                 # 使用、配置、排障和维护文档
├── chzzk/                # CHZZK 录制入口
├── douyin/               # 抖音录制脚本和 DouyinLiveRecorder 子模块
│   ├── get_stream.py     # 抖音直播源解析辅助脚本
│   ├── record.ps1        # Windows PowerShell 录制入口
│   └── record.sh         # Linux / macOS 录制入口
├── soop/                 # SOOP 录制脚本
├── kick/                 # Kick 录制入口
├── scripts/              # 多平台共享录制内核
├── systemd/              # WebUI systemd unit 与安装脚本
├── tk/                   # TikTok 录制脚本
├── twitch/               # Twitch -> Bilibili 脚本
├── youtube/              # YouTube 录制入口
├── webui/                # 本地录制任务管理页面与 API
├── start.sh              # TikTok 直播源检测入口
└── yt.sh                 # YouTube -> Bilibili 脚本
```

## 运行产物

脚本会在运行目录下生成账号目录、分段视频和日志。仓库已经忽略以下运行产物：

- `logs/`
- `*.log`
- `*.mp4`
- `*.flv`
- `*.mkv`
- `*.ts`
- `recordings/`
- `cookies.txt`

建议在仓库外或 `recordings/` 下运行长期录制任务，避免源码目录被账号目录和视频文件淹没。

## 子模块

`douyin/DouyinLiveRecorder` 是 Git 子模块。首次克隆后需要初始化：

```bash
git submodule update --init --recursive
```

更新子模块：

```bash
git submodule update --remote douyin/DouyinLiveRecorder
```
