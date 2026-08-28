import { reactive } from "vue";
import { taskService } from "../services/taskService.js";

export const taskState = reactive({
  jobs: [],
  query: "",
  stateFilter: "all",
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
export function stopTask(unit) { return taskService.stop(unit); }
export function restartTask(unit) { return taskService.restart(unit); }
export function fetchTaskLogs(unit, tail) { return taskService.logs(unit, tail); }
