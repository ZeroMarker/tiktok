// main.js — 入口：注册 Material 组件与本页组件、挂全局样式、启动轮询与 PWA。
import "./material.js";
import { refresh } from "./actions.js";
import { globalStyles } from "./styles.js";
import "./components/bili-app.js";
import "./components/status-card.js";
import "./components/live-card.js";
import "./components/replay-card.js";
import "./components/room-card.js";
import "./components/logs-card.js";

document.adoptedStyleSheets = [...document.adoptedStyleSheets, globalStyles.styleSheet];

refresh();
setInterval(() => refresh(true), 10000);
// 切回标签页立即刷新一次，不等下一个 10 秒周期（后台期间轮询是暂停的）
document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(true); });
window.addEventListener("online", () => refresh(true));

// PWA：离线壳；注册失败不能影响控制台本身
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
