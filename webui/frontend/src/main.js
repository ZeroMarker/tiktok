// main.js — 应用入口：挂载 Vue、注册 SW、在线状态、轮询。
import { createApp } from "vue";
import App from "./App.vue";
import "./styles.css";
import { refreshAll, state } from "./store.js";

createApp(App).mount("#app");

// PWA：服务线程缓存应用壳（单文件构建），API 始终走网络。
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("./sw.js")
      .then((reg) => {
        reg.addEventListener("updatefound", () => {
          const nw = reg.installing;
          if (!nw) return;
          nw.addEventListener("statechange", () => {
            if (nw.state === "installed" && navigator.serviceWorker.controller) {
              // 新版本已就绪；由 header 的提示条处理，这里不阻塞。
            }
          });
        });
      })
      .catch(() => {});
  });
}

// 在线/离线：离线显示缓存，联网自动刷新。
window.addEventListener("offline", () => {
  state.offline = true;
  state.degraded = false;
});
window.addEventListener("online", () => {
  state.offline = false;
  refreshAll();
});

// 首次加载 + 周期轮询。
refreshAll();
setInterval(() => refreshAll(), 5000);
