// utils.js — 通用格式化与 URL 构造。
export { PLATFORM_ZH, LOGO_COLORS, QUALITY_ZH, QUALITIES } from "./config/platforms.js";

export function fmtBytes(n) {
  if (!Number.isFinite(+n)) return "—";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1024 && i < u.length - 1) {
    n /= 1024;
    i++;
  }
  return n.toFixed(i > 1 ? 1 : 0) + " " + u[i];
}

export function stateLabel(s, sub) {
  const m = {
    active: { running: "运行中", activating: "启动中", deactivating: "停止中" },
    activating: { "auto-restart": "重启中", start: "启动中", reload: "重载中" },
    // 停止过程中 systemd 上报的是 deactivating + stop-sigterm 之类的 SubState
    deactivating: {
      "stop-sigterm": "停止中",
      "final-sigterm": "停止中",
      "stop-sigkill": "强制停止中",
      "final-sigkill": "强制停止中",
      "stop-post": "停止中",
      stop: "停止中",
    },
    inactive: { dead: "已停止" },
    failed: { failed: "已失败" },
    paused: { paused: "已暂停" },
  };
  const t = m[s] && m[s][sub];
  if (t) return t;
  if (s === "deactivating") return "停止中";
  if (s === "paused") return "已暂停";
  if (s === "failed") return "失败";
  if (s === "activating") return "启动中";
  return s;
}

/** 该单元是否正在停止：systemd 收尾期间 ActiveState=deactivating、SubState=stop-*。
 *  引擎收尾当前分段通常几秒，最坏受单元 TimeoutStopSec（30s）约束。 */
export function isStopping(job) {
  if (!job) return false;
  const sub = String(job.substate || "");
  return job.state === "deactivating" || sub === "stop" || sub.startsWith("stop-") || sub.startsWith("final-");
}

/** 该任务是否已暂停：单元被 systemd 回收，仅存在于后端任务目录。 */
export function isPaused(job) {
  return Boolean(job) && job.state === "paused";
}

export function stateClass(s, sub) {
  if (s === "failed") return "b-bad";
  if (s === "active") return sub === "running" ? "b-good" : sub === "activating" ? "b-warn" : "b-info";
  if (s === "paused" || s === "inactive" || s === "dead") return "b-muted";
  if (s === "activating" || s === "deactivating") return "b-warn";
  return "b-info";
}

export function liveLabel(live) {
  if (live === "live") return "直播中";
  if (live === "waiting") return "等待开播";
  if (live === "offline") return "未开播";
  if (live === "paused") return "已暂停";
  return "直播状态未知";
}
export function liveClass(live) {
  if (live === "live") return "b-live";
  if (live === "waiting") return "b-warn";
  if (live === "offline" || live === "paused") return "b-muted";
  return "b-info";
}

export function fmtTime(s) {
  if (!s) return "启动时间未知";
  const d = new Date(s);
  return isNaN(d) ? s : d.toLocaleString();
}

export function fmtUptime(s) {
  if (!s) return "";
  const t = new Date(s).getTime();
  if (isNaN(t)) return "";
  let sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  const d = Math.floor(sec / 86400);
  sec %= 86400;
  const h = Math.floor(sec / 3600);
  sec %= 3600;
  const m = Math.floor(sec / 60);
  if (d) return `${d}天${h}小时`;
  if (h) return `${h}小时${m}分`;
  if (m) return `${m}分钟`;
  return "刚刚";
}

export function fileUrl(path) {
  return "api/file?path=" + encodeURIComponent(path);
}
