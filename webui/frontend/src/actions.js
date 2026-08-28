// actions.js — 统一的任务/文件操作（确认、请求、反馈、刷新）。
import { confirmDialog, toast } from "./ui.js";
import { navigate } from "./router.js";
import { stopJob, restartJob, deleteFile, refreshAll, state } from "./store.js";

export function openJob(job) {
  state.selectedUnit = job.unit;
  navigate("/tasks/" + encodeURIComponent(job.unit));
}

export function askStop(job, cb) {
  confirmDialog("停止任务", "确定停止此录制任务？当前 MP4 将正常收尾。", "停止", async () => {
    try {
      await stopJob(job.unit);
      toast("停止请求已发送");
      await refreshAll();
      cb && cb();
    } catch (e) {
      toast(e.message);
    }
  });
}

export function askRestart(job, cb) {
  confirmDialog("重启任务", "确定重启此录制任务？录制进程将被终止并重新拉起。", "重启", async () => {
    try {
      await restartJob(job.unit);
      toast("重启请求已发送");
      await refreshAll();
      cb && cb();
    } catch (e) {
      toast(e.message);
    }
  });
}

export function askDeleteFile(f, cb) {
  confirmDialog("删除文件", "确定删除「" + f.name + "」吗？此操作不可恢复。", "删除", async () => {
    try {
      await deleteFile(f.path);
      toast("文件已删除");
      await refreshAll();
      cb && cb();
    } catch (e) {
      toast(e.message);
    }
  });
}

export function confirmAndRun(title, text, okText, fn) {
  confirmDialog(title, text, okText, async () => {
    try {
      await fn();
    } catch (e) {
      toast(e.message);
    }
  });
}
