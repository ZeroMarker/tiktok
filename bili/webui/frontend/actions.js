// actions.js — 用户操作与刷新：串行执行、统一提示、操作后刷新状态。
import * as api from "./api.js";
import { HINT, set, state } from "./store.js";

let toastSeq = 0;
let toastTimer = null;

/** 横幅 + toast 同时提示；超时后 toast 消失、横幅恢复默认说明（错误不会永久占屏）。 */
export function notify(text, error = false) {
  const id = ++toastSeq;
  set({ notice: { text, error }, toast: { text, error, id } });
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    if (state.toast?.id === id) set({ toast: null });
    if (state.notice.text === text) set({ notice: { text: HINT, error: false } });
  }, error ? 8000 : 4000);
}

export function dismissToast() {
  clearTimeout(toastTimer);
  set({ toast: null });
}

export const fail = (e) => notify("错误：" + e.message, true);

let loading = false;

/** 拉 /api/status。background=true 时有操作在跑或标签页在后台就跳过，失败也不弹错。 */
export async function refresh(background = false) {
  if (loading || (background && (state.busy || document.hidden))) return;
  loading = true;
  try {
    const status = await api.fetchStatus();
    set({ status, online: true, refreshedAt: new Date().toLocaleTimeString() });
  } catch (e) {
    set({ online: false });
    if (!background) fail(e);
  } finally {
    loading = false;
  }
}

/**
 * 执行一项用户操作：同一时间只允许一项（后端也有控制锁，冲突返回 409）。
 * fn 返回字符串则作为成功提示；抛错统一提示。结束后刷新状态。
 */
export async function run(name, fn, { reload = true } = {}) {
  if (state.busy) return;
  set({ busy: name });
  try {
    const message = await fn();
    if (message) notify(message);
  } catch (e) {
    fail(e);
  } finally {
    set({ busy: null });
  }
  if (reload) await refresh();
}
