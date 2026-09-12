import { confirmDialog, toast } from "../../ui.js";
import { navigate } from "../../router.js";
import { taskState, pauseTask, resumeTask, restartTask, removeTask } from "../../stores/taskStore.js";
import { refreshAll } from "../../stores/syncStore.js";

export function openTask(job) {
  taskState.selectedUnit = job.unit;
  navigate("/tasks/" + encodeURIComponent(job.unit));
}

/** 统一的控制动作包装：标记 pending → 调接口 → 刷新 → 还原 pending。 */
async function runAction(job, action, request, done, cb) {
  taskState.pendingUnit = job.unit;
  taskState.pendingAction = action;
  try {
    await request();
    toast(done);
    await refreshAll({ includeFiles: false });
    cb && cb();
  } catch (error) {
    toast(error.message);
  } finally {
    taskState.pendingUnit = "";
    taskState.pendingAction = "";
  }
}

export function askPause(job, cb) {
  confirmDialog("暂停任务", "暂停后录制进程会先收尾当前分段再退出（最长 30 秒），任务保留在列表中，可随时「继续」。", "暂停", () =>
    runAction(job, "pause", () => pauseTask(job.unit), "任务已暂停，可随时继续", cb)
  );
}

export function askResume(job, cb) {
  runAction(job, "resume", () => resumeTask(job.unit), "任务已继续，开始等待开播", cb);
}

export function askRestart(job, cb) {
  confirmDialog("重启任务", "确定重启此录制任务？录制进程将被终止并重新拉起（当前分段收尾最长 30 秒）。", "重启", () =>
    runAction(job, "restart", () => restartTask(job.unit), "重启完成", cb)
  );
}

export function askDeleteTask(job, cb) {
  confirmDialog(
    "删除任务",
    `确定删除「${job.target}」的录制任务？任务会停止并从列表移除；已录制的文件不会被删除，仍可在「录制文件」中查看。`,
    "删除",
    () => runAction(job, "delete", () => removeTask(job.unit), "任务已删除，录制文件已保留", cb)
  );
}
