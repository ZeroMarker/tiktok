import { api } from "../api.js";

export const taskService = {
  list: () => api("api/jobs"),
  start: (form) => api("api/start", { method: "POST", body: JSON.stringify(form) }),
  stop: (unit) => api("api/stop", { method: "POST", body: JSON.stringify({ unit }) }),
  restart: (unit) => api("api/restart", { method: "POST", body: JSON.stringify({ unit }) }),
  logs: async (unit, tail) => (await api("api/logs?unit=" + encodeURIComponent(unit) + "&tail=" + tail)).logs || "",
};
