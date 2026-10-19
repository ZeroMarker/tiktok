// ui.js — 全局轻 UI 状态：toast、确认框。
import { createStore } from "./stores/store.js";

export const ui = createStore({
  toast: "",
  confirm: { visible: false, title: "", text: "", okText: "确认", danger: false, cb: null },
});

let toastTimer = 0;

export function toast(msg) {
  ui.toast = msg;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { ui.toast = ""; }, 2500);
}

export function confirmDialog(title, text, okText, cb, danger = true) {
  ui.confirm = { visible: true, title, text, okText: okText || "确认", danger, cb };
}

export function closeConfirm() {
  ui.confirm = { visible: false, title: "", text: "", okText: "确认", danger: true, cb: null };
}
