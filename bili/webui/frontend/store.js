// store.js — 全页共享状态（极简发布订阅）。组件经 base.js 订阅，任何 set 都触发重渲染。
//
// status   /api/status 最近一次成功结果（null = 还没拿到过）
// online   最近一次刷新是否成功；失败时界面保留上次结果并标明
// busy     正在执行的用户操作名（null = 空闲）；同一时间只允许一项，所有控件随之禁用
// notice   顶部横幅 {text, error}；toast 同步显示，超时后横幅恢复默认说明
const listeners = new Set();

export const HINT = "固定一个 TikTok 主播转推；开播自动起推流、关播自动停推流。也可切到文件轮播。";

export const state = {
  status: null,
  online: true,
  refreshedAt: "",
  busy: null,
  notice: { text: HINT, error: false },
  toast: null, // {text, error, id}
};

export function set(patch) {
  Object.assign(state, patch);
  for (const fn of listeners) fn();
}

export function subscribe(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
