import { confirmDialog, toast } from "../../ui.js";
import { navigate } from "../../router.js";
import { taskState, stopTask, restartTask } from "../../stores/taskStore.js";
import { refreshAll } from "../../stores/syncStore.js";

export function openTask(job) {
  taskState.selectedUnit = job.unit;
  navigate("/tasks/" + encodeURIComponent(job.unit));
}

export function askStop(job, cb) {
  confirmDialog("停止任务", "确定停止此录制任务？当前 MP4 将正常收尾。", "停止", async () => {
    taskState.pendingUnit = job.unit;
    taskState.pendingAction = "stop";
    try {
      await stopTask(job.unit);
      toast("停止请求已发送");
      await refreshAll({ includeFiles: false });
      cb && cb();
    } catch (error) {
      toast(error.message);
    } finally {
      taskState.pendingUnit = "";
      taskState.pendingAction = "";
    }
  });
}

export function askRestart(job, cb) {
  confirmDialog("重启任务", "确定重启此录制任务？录制进程将被终止并重新拉起。", "重启", async () => {
    taskState.pendingUnit = job.unit;
    taskState.pendingAction = "restart";
    try {
      await restartTask(job.unit);
      toast("重启请求已发送");
      await refreshAll({ includeFiles: false });
      cb && cb();
    } catch (error) {
      toast(error.message);
    } finally {
      taskState.pendingUnit = "";
      taskState.pendingAction = "";
    }
  });
}
