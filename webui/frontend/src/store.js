// store.js — 全局响应式状态：轮询刷新、离线快照、连接中断降级。
import { reactive } from "vue";
import { api } from "./api.js";

const SNAPSHOT_KEY = "livestream-webui-snapshot-v1";

export const state = reactive({
  jobs: [],
  overview: {
    running: 0,
    jobs: 0,
    failed: 0,
    disk_total: 0,
    disk_used: 0,
    disk_free: 0,
    disk_percent: 0,
    platforms: {},
    load: [],
    mem_total: 0,
    mem_available: 0,
    server_time: 0,
  },
  files: [],
  filesTotal: 0,
  selectedUnit: "",
  stateFilter: "all",
  jobQuery: "",
  offline: false,
  degraded: false,
  busy: false,
  loadedOnce: false,
  lastSynced: null,
  installPrompt: null,
});

export function cacheSnapshot() {
  try {
    localStorage.setItem(
      SNAPSHOT_KEY,
      JSON.stringify({
        savedAt: Date.now(),
        jobs: state.jobs,
        overview: state.overview,
        files: state.files,
        filesTotal: state.filesTotal,
      })
    );
  } catch {
    /* 私密模式/配额不足时忽略 */
  }
}

export function restoreSnapshot() {
  try {
    const s = JSON.parse(localStorage.getItem(SNAPSHOT_KEY) || "null");
    if (!s) return false;
    state.jobs = s.jobs || [];
    state.overview = s.overview || state.overview;
    state.files = s.files || [];
    state.filesTotal = s.filesTotal || 0;
    state.loadedOnce = true;
    return true;
  } catch {
    return false;
  }
}

export async function refreshAll() {
  if (state.busy) return;
  state.busy = true;
  try {
    const [jobs, overview, fd] = await Promise.all([
      api("api/jobs"),
      api("api/overview"),
      api("api/files?limit=300"),
    ]);
    state.jobs = jobs;
    state.overview = overview;
    state.files = fd.files;
    state.filesTotal = fd.total;
    state.degraded = false;
    state.lastSynced = Date.now();
    state.loadedOnce = true;
    cacheSnapshot();
  } catch (e) {
    if (!navigator.onLine) {
      state.offline = true;
      restoreSnapshot();
    } else {
      state.degraded = true;
    }
  } finally {
    state.busy = false;
  }
}

export async function postJob(url, body) {
  return api(url, { method: "POST", body: JSON.stringify(body) });
}

export async function stopJob(unit) {
  return postJob("api/stop", { unit });
}
export async function restartJob(unit) {
  return postJob("api/restart", { unit });
}
export async function deleteFile(path) {
  return postJob("api/delete", { path });
}
export async function startJob(form) {
  return postJob("api/start", form);
}
export async function logs(unit, tail) {
  const d = await api("api/logs?unit=" + encodeURIComponent(unit) + "&tail=" + tail);
  return d.logs || "";
}
