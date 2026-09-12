import { reactive } from "vue";
import { taskService } from "../services/taskService.js";

export const taskState = reactive({
  jobs: [],
  query: "",
  stateFilter: "all",
  liveFilter: "all",
  platformFilter: "all",
  selectedUnit: "",
  pendingUnit: "",
  pendingAction: "",
  error: "",
});

export async function refreshTasks() {
  try {
    taskState.jobs = await taskService.list();
    taskState.error = "";
    return taskState.jobs;
  } catch (error) {
    taskState.error = error.message || "任务同步失败";
    throw error;
  }
}

export function startTask(form) { return taskService.start(form); }
export function pauseTask(unit) { return taskService.pause(unit); }
export function resumeTask(unit) { return taskService.resume(unit); }
export function restartTask(unit) { return taskService.restart(unit); }
export function removeTask(unit) { return taskService.remove(unit); }
export function fetchTaskLogs(unit, tail) { return taskService.logs(unit, tail); }
