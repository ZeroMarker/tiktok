import { appState } from "./appStore.js";
import { taskState, refreshTasks } from "./taskStore.js";
import { overviewState, refreshOverview } from "./overviewStore.js";
import { recordingState, refreshRecordings } from "./recordingStore.js";

const SNAPSHOT_KEY = "livestream-webui-snapshot-v1";

function messageOf(error, fallback) { return error && error.message ? error.message : fallback; }

export function cacheSnapshot() {
  try {
    localStorage.setItem(SNAPSHOT_KEY, JSON.stringify({
      savedAt: Date.now(),
      jobs: taskState.jobs,
      overview: overviewState,
      files: recordingState.files,
      filesTotal: recordingState.total,
      filesOffset: recordingState.offset,
      filesQuery: recordingState.query,
    }));
  } catch { /* 私密模式或配额不足 */ }
}

export function restoreSnapshot() {
  try {
    const snapshot = JSON.parse(localStorage.getItem(SNAPSHOT_KEY) || "null");
    if (!snapshot) return false;
    taskState.jobs = snapshot.jobs || [];
    Object.assign(overviewState, snapshot.overview || {});
    recordingState.files = snapshot.files || [];
    recordingState.total = snapshot.filesTotal || 0;
    recordingState.offset = snapshot.filesOffset || 0;
    recordingState.query = snapshot.filesQuery || "";
    appState.loadedOnce = true;
    return true;
  } catch { return false; }
}

export async function refreshAll({ includeFiles = true } = {}) {
  if (appState.busy) return;
  appState.busy = true;
  appState.errors.jobs = "";
  appState.errors.overview = "";
  if (includeFiles) appState.errors.files = "";
  const requests = [refreshTasks(), refreshOverview()];
  if (includeFiles) requests.push(refreshRecordings({ query: recordingState.query, offset: 0 }));
  try {
    const results = await Promise.allSettled(requests);
    const [jobs, overview, files] = results;
    if (jobs.status === "rejected") appState.errors.jobs = messageOf(jobs.reason, "任务同步失败");
    if (overview.status === "rejected") appState.errors.overview = messageOf(overview.reason, "概览同步失败");
    if (includeFiles && files.status === "rejected") appState.errors.files = messageOf(files.reason, "文件同步失败");
    const hasSuccess = results.some((result) => result.status === "fulfilled");
    appState.degraded = !hasSuccess || Object.values(appState.errors).some(Boolean);
    if (hasSuccess) {
      appState.offline = false;
      appState.lastSynced = Date.now();
      appState.loadedOnce = true;
      cacheSnapshot();
    } else if (!navigator.onLine) {
      appState.offline = true;
      restoreSnapshot();
    }
  } finally {
    appState.busy = false;
  }
}
