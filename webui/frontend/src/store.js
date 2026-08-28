// store.js — 全局响应式状态：轮询刷新、离线快照、连接中断降级。
import { reactive } from "vue";
import { api } from "./api.js";

const SNAPSHOT_KEY = "livestream-webui-snapshot-v1";
let filesRequestId = 0;

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
  filesOffset: 0,
  filesLimit: 80,
  filesQuery: "",
  selectedUnit: "",
  stateFilter: "all",
  platformFilter: "all",
  jobQuery: "",
  offline: false,
  degraded: false,
  busy: false,
  filesBusy: false,
  pendingUnit: "",
  pendingAction: "",
  errors: { jobs: "", overview: "", files: "" },
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
        filesOffset: state.filesOffset,
        filesQuery: state.filesQuery,
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
    state.filesOffset = s.filesOffset || 0;
    state.filesQuery = typeof s.filesQuery === "string" ? s.filesQuery : "";
    state.loadedOnce = true;
    return true;
  } catch {
    return false;
  }
}

export async function refreshAll({ includeFiles = true } = {}) {
  if (state.busy) return;
  state.busy = true;
  state.errors.jobs = "";
  state.errors.overview = "";
  try {
    const requests = [api("api/jobs"), api("api/overview")];
    if (includeFiles) requests.push(refreshFiles({ query: state.filesQuery, offset: 0, silent: true }));
    const results = await Promise.allSettled(requests);

    const [jobsResult, overviewResult, filesResult] = results;
    if (jobsResult.status === "fulfilled") state.jobs = jobsResult.value;
    else state.errors.jobs = messageOf(jobsResult.reason, "任务同步失败");
    if (overviewResult.status === "fulfilled") state.overview = overviewResult.value;
    else state.errors.overview = messageOf(overviewResult.reason, "概览同步失败");
    if (includeFiles && filesResult.status === "rejected" && !state.errors.files) {
      state.errors.files = messageOf(filesResult.reason, "文件同步失败");
    }

    const hasSuccess = results.some((result) => result.status === "fulfilled");
    state.degraded = !hasSuccess || Object.values(state.errors).some(Boolean);
    if (hasSuccess) {
      state.offline = false;
      state.lastSynced = Date.now();
      state.loadedOnce = true;
      cacheSnapshot();
    } else if (!navigator.onLine) {
      state.offline = true;
      restoreSnapshot();
    }
  } finally {
    state.busy = false;
  }
}

function messageOf(error, fallback) {
  return error && error.message ? error.message : fallback;
}

export async function refreshFiles({ query = state.filesQuery, offset = 0, append = false, silent = false } = {}) {
  if (state.filesBusy && !silent) return;
  if (!silent) state.filesBusy = true;
  state.errors.files = "";
  const requestId = ++filesRequestId;
  try {
    const normalizedQuery = String(query || "").trim();
    const d = await api(
      "api/files?q=" + encodeURIComponent(normalizedQuery) +
        "&limit=" + state.filesLimit + "&offset=" + Math.max(0, Number(offset) || 0)
    );
    if (requestId !== filesRequestId) return d;
    state.files = append ? [...state.files, ...(d.files || [])] : d.files || [];
    state.filesTotal = Number(d.total) || 0;
    state.filesOffset = Math.max(0, Number(offset) || 0) + (d.files || []).length;
    state.filesQuery = normalizedQuery;
    return d;
  } catch (error) {
    if (requestId === filesRequestId) state.errors.files = messageOf(error, "文件同步失败");
    throw error;
  } finally {
    if (!silent && requestId === filesRequestId) state.filesBusy = false;
  }
}

export async function loadMoreFiles() {
  if (state.filesBusy || state.files.length >= state.filesTotal) return;
  return refreshFiles({ query: state.filesQuery, offset: state.filesOffset, append: true });
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
