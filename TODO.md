# 待办

- [ ] 等待无直播录制时部署并重启 WebUI，使 TikTok 首轮兜底和离线状态修复（`ec9fbed`）生效。
  - 执行前确认所有任务均未处于录制状态，且 `livestream-webui.service` 下没有运行中的 ffmpeg 录制进程；有录制时继续等待。
  - 确认本机 `main` 已包含修复提交，执行 `sudo systemctl restart livestream-webui.service`。
  - 重启后检查服务状态与任务日志，确认首轮兜底正常、浏览器确认离线时显示“未开播”，再勾选完成。
