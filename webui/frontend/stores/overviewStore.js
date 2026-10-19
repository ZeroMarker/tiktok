// overviewStore.js — 概览指标（实时状态、磁盘、平台分布、最近文件）。
import { createStore } from "./store.js";
import { api } from "../api.js";

export const overviewState = createStore({
  running: 0,
  live: 0,
  waiting: 0,
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
  Object.assign(overviewState, await api("api/overview"));
  return overviewState;
}
