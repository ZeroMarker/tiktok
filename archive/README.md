# 封存脚本（2026-09-28）

这些脚本曾放在仓库根目录，现已**移出根目录封存**。功能未被移除，仍可直接调用，
只是不再作为文档里的推荐入口。

| 脚本 | 原用途 | 现状与替代 |
|------|--------|-----------|
| `start.sh` | TikTok 直播源快速检测（只判断能不能取到流，不录制） | 已被统一引擎取代。检测能力现在在 `platforms/tiktok/record.sh` 与 WebUI 概览页（`live` 字段）里 |
| `yt.sh` | YouTube 直播源 → Bilibili 转推 | 已被 `bili/push.sh` 与 `bili/soop.sh` 的转推链路取代。B 站转推统一走 `bili/` |

封存原因：根目录按平台平铺了 6 个目录 + 2 个散脚本，可读性差。平台相关的脚本已
归入 [`platforms/`](../platforms/)，跨平台/转推相关的归入 [`bili/`](../bili/README.md)，
历史排障文档归入 [`docs/archive/`](../docs/archive/)。

## 仍要用的旧命令怎么改

```bash
# 旧：bash start.sh <username>
bash platforms/tiktok/record.sh <username>     # 顺带录制

# 旧：bash yt.sh <handle>
# 新：见 bili/README.md 的推流章节（push.sh / watch.sh / 管理页）
```

若确实还需要这两个脚本的历史行为，直接调用本目录下的文件即可：

```bash
bash archive/start.sh <username>
bash archive/yt.sh <handle>
```

注意：这两个脚本**不含平台适配逻辑**（没有 cookie 自动附带、没有画质与分段参数、
`yt.sh` 也没有断线重抓），而 `platforms/*/record.sh` 与 `bili/*.sh` 都有。长期录制
请用后者。
