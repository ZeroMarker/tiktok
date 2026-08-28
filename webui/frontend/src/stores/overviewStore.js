import { reactive } from "vue";
import { api } from "../api.js";

export const overviewState = reactive({
  running: 0,
  jobs: 0,
  failed: 0,
  disk_total: 0,
  disk_used: 0,
  disk_free: 0,
  disk_percent: 0,
  platforms: {},
  files: [],
  load: [],
  mem_total: 0,
  mem_available: 0,
  server_time: 0,
});

export async function refreshOverview() {
  try {
    Object.assign(overviewState, await api("api/overview"));
    return overviewState;
  } catch (error) {
    throw error;
  }
}
