import { api } from "../api.js";

// 任务控制接口：暂停/继续/重启/删除都要等 systemd 收敛（单元 TimeoutStopSec=30s），
// 因此单独放宽超时，避免前端先把"仍在收尾"报成失败。
const CONTROL = { method: "POST", timeout: 40000 };

export const taskService = {
  list: () => api("api/jobs"),
  start: (form) => api("api/start", { method: "POST", body: JSON.stringify(form) }),
  pause: (unit) => api("api/pause", { ...CONTROL, body: JSON.stringify({ unit }) }),
  resume: (unit) => api("api/resume", { ...CONTROL, body: JSON.stringify({ unit }) }),
  restart: (unit) => api("api/restart", { ...CONTROL, body: JSON.stringify({ unit }) }),
  remove: (unit) => api("api/delete-task", { ...CONTROL, body: JSON.stringify({ unit }) }),
  logs: async (unit, tail) => (await api("api/logs?unit=" + encodeURIComponent(unit) + "&tail=" + tail)).logs || "",
};
