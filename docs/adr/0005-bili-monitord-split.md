# ADR 0005：把 Bili 值守从管理页进程里拆出来（bili-monitord）

- 状态：已采纳
- 日期：2026-10-19
- 范围：`bili/`（`pushctl.py`、`monitord.py`、`webui/app.py`、`systemd/`）。前端契约基本不变
  （`/api/status` 的 `target` 多一个 `monitor` 字段，日志选择多一个「值守」）。
- 相关：[ADR 0002](0002-recorderd-split.md)（录制侧同类拆分）

## 背景

改造前 `bili-webui.service` 一个进程既提供管理页，又在后台线程里跑值守（开播自动起推流、
下播自动停推流并关播、房间被关时重新开播）。值守因此跟着管理页的生命周期走。

2026-10-19 04:17 管理页进程被直接 SIGTERM（不是 `systemctl stop`，与 ADR 0002 记录的
`pkill -f webui/app.py` 误操作同一天，路径 `bili/webui/app.py` 同样命中）。单元当时是
`Restart=on-failure`，SIGTERM 退出算正常退出，不重启。值守随之停了约 9 小时，主播再开播时
没人起推流、没人开房间，B 站直播一直停着。

## 决策

值守是后端的事，独立成服务：

```
bili-monitord.service   bili/monitord.py
  ├── 每 60s 一轮；SIGUSR1 立即一轮
  └── ~/.config/bili/monitord.json 的唯一写入者（值守快照）

bili-webui.service      bili/webui/app.py
  ├── 静态资源 + /api/*：展示状态、执行用户操作
  ├── 值守状态只读 monitord.json；「立即检测」= systemctl kill -s USR1 bili-monitord
  └── 不含任何值守逻辑（有测试钉住）

bili/pushctl.py          两者共用的后端库：systemd、配置、开播、验流、控制锁
```

- **进程间只经文件交互**，不加 socket/端口：配置 `*.env`、快照 `monitord.json`
  （原子写）、控制锁 `control.lock`（flock，非阻塞；用户操作拿不到返回 409，值守拿不到本轮让路）。
- **清零下播计数**原先由管理页直接改内存里的 streak；现在管理页每次开值守在 `auto.env`
  写新的 `EPOCH`，monitord 见到纪元变化自己清零。快照始终只有一个写入者。
- monitord 的 `streak` / `close_pending` 落盘，重启后恢复，不会丢掉「关播失败待重试」。
- 两个单元都 `Restart=always`：被直接杀掉也会拉回来。

## 取舍

- 多一个常驻进程（约 10 MB）。
- 管理页看到的状态最多滞后一轮（60s），与改造前相同；用户操作后会主动发 SIGUSR1 刷新。
- monitord 没在跑时，看板 `live` 显示未知并标明「值守服务未运行」，不拿旧快照冒充当前状态。

## 升级与回滚

`bash bili/systemd/install.sh`：先重启管理页（换掉带监测线程的旧进程），再
`enable --now bili-monitord`，避免两边同时接管。回滚：`git checkout <旧提交>`，
`systemctl --user disable --now bili-monitord`，再重启 `bili-webui`。
