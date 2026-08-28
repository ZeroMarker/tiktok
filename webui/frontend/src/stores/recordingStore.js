import { reactive } from "vue";
import { recordingService } from "../services/recordingService.js";

export const recordingState = reactive({
  files: [],
  total: 0,
  offset: 0,
  limit: 80,
  query: "",
  busy: false,
  error: "",
  pendingPath: "",
});

let requestId = 0;

export async function refreshRecordings({ query = recordingState.query, offset = 0, append = false } = {}) {
  if (recordingState.busy && append) return;
  recordingState.busy = true;
  recordingState.error = "";
  const currentRequest = ++requestId;
  try {
    const data = await recordingService.list({ query: String(query || "").trim(), limit: recordingState.limit, offset });
    if (currentRequest !== requestId) return data;
    const files = data.files || [];
    recordingState.files = append ? [...recordingState.files, ...files] : files;
    recordingState.total = Number(data.total) || 0;
    recordingState.offset = Math.max(0, Number(offset) || 0) + files.length;
    recordingState.query = String(query || "").trim();
    return data;
  } catch (error) {
    if (currentRequest === requestId) recordingState.error = error.message || "文件同步失败";
    throw error;
  } finally {
    if (currentRequest === requestId) recordingState.busy = false;
  }
}

export function loadMoreRecordings() {
  if (recordingState.busy || recordingState.files.length >= recordingState.total) return Promise.resolve();
  return refreshRecordings({ query: recordingState.query, offset: recordingState.offset, append: true });
}

export function deleteRecording(path) { return recordingService.delete(path); }
