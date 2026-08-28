// utils.js — 平台文案、状态语义、格式化、URL 构造。
export const PLATFORM_ZH = {
  tiktok: "TikTok",
  douyin: "抖音",
  soop: "SOOP",
  kick: "Kick",
  youtube: "YouTube",
  chzzk: "CHZZK",
};
export const LOGO_COLORS = {
  tiktok: "#fb7185",
  douyin: "#f43f5e",
  soop: "#60a5fa",
  kick: "#4ade80",
  youtube: "#f87171",
  chzzk: "#2dd4bf",
};
export const QUALITY_ZH = { best: "原画", "1080p": "1080p", "720p": "720p", "480p": "480p" };
export const QUALITIES = ["best", "1080p", "720p", "480p"];

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
    inactive: { dead: "已停止" },
    failed: { failed: "已失败" },
  };
  const t = m[s] && m[s][sub];
  return t || (s === "failed" ? "失败" : s);
}

export function stateClass(s, sub) {
  if (s === "failed") return "b-bad";
  if (s === "active") return sub === "running" ? "b-good" : sub === "activating" ? "b-warn" : "b-info";
  if (s === "inactive" || s === "dead") return "b-muted";
  if (s === "activating" || s === "deactivating") return "b-warn";
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
