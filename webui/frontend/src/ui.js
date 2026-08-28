// ui.js — 全局轻 UI 状态：toast、确认框。
import { reactive } from "vue";

export const ui = reactive({
  toast: "",
  toastTimer: 0,
  confirm: { visible: false, title: "", text: "", okText: "确认", danger: false, cb: null },
});

export function toast(msg) {
  ui.toast = msg;
  clearTimeout(ui.toastTimer);
  ui.toastTimer = setTimeout(() => (ui.toast = ""), 2500);
}

export function confirmDialog(title, text, okText, cb, danger = true) {
  ui.confirm = { visible: true, title, text, okText: okText || "确认", danger, cb };
}

export function closeConfirm() {
  ui.confirm = { visible: false, title: "", text: "", okText: "确认", danger: true, cb: null };
}
