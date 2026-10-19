// appStore.js — 全局连接/同步状态。
import { createStore } from "./store.js";

export const appState = createStore({
  offline: false,
  degraded: false,
  busy: false,
  errors: { jobs: "", overview: "", files: "" },
  loadedOnce: false,
  lastSynced: null,
  installPrompt: null,
});
