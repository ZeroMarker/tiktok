import { confirmDialog, toast } from "../../ui.js";
import { deleteRecording, recordingState } from "../../stores/recordingStore.js";
import { refreshAll } from "../../stores/syncStore.js";

export function askDeleteRecording(file, cb) {
  confirmDialog("删除文件", `确定删除「${file.name}」吗？此操作不可恢复。`, "删除", async () => {
    recordingState.pendingPath = file.path;
    try {
      await deleteRecording(file.path);
      toast("文件已删除");
      await refreshAll({ includeFiles: true });
      cb && cb();
    } catch (error) {
      toast(error.message);
    } finally {
      recordingState.pendingPath = "";
    }
  });
}
