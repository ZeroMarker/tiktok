// ui.js — 共用渲染片段：图标、按钮转圈、单元状态文案、确认对话框。
import { html, nothing, svg } from "lit";
import { state } from "./store.js";

const ICONS = {
  logo: "M17 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 4v-11l-4 4z",
  refresh: "M17.65 6.35A8 8 0 1 0 19.73 14h-2.08a6 6 0 1 1-1.41-6.24L13 11h7V4l-2.35 2.35z",
  status: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-2 14.5v-9l7.5 4.5-7.5 4.5z",
  live: "M9.75 15.02 15.5 12l-5.75-3.02v6.04zM18 3H6a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3h12a3 3 0 0 0 3-3V6a3 3 0 0 0-3-3zm1 15a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1h12a1 1 0 0 1 1 1v12z",
  replay: "M4 6h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1zm1 2v8h14V8H5zm3 2v4l3.5-2L8 10z",
  room: "M12 3 2 8.5V9h20v-.5L12 3zM5 10v8H3v3h18v-3h-2v-8h-3v8h-3v-8h-3v8H7v-8H5z",
  logs: "M4 5h16a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H8l-5 4V6a1 1 0 0 1 1-1zm2 3v2h12V8H6zm0 4v2h8v-2H6z",
};

export const icon = (name, size = 16) =>
  html`<svg width=${size} height=${size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">${svg`<path d=${ICONS[name]}></path>`}</svg>`;

/** 正在执行的那项操作在按钮上转圈（长操作如验流 ≤150s 不再"看起来卡死"）。用法：<md-… ?has-icon=${spinning(n)}>${spinner(n)}… */
export const spinning = (name) => state.busy === name;
export const spinner = (name) =>
  spinning(name) ? html`<md-circular-progress slot="icon" indeterminate></md-circular-progress>` : nothing;

export const cardHead = (iconName, title, kicker, tag) => html`
  <div class="card-head">
    <div><h2>${icon(iconName)}${title}</h2><div class="card-kicker">${kicker}</div></div>
    ${tag ? html`<span class="pill">${tag}</span>` : nothing}
  </div>`;

export const unitLine = (u) =>
  `${u.active}/${u.sub}${u.pid ? " pid=" + u.pid : ""}${u.pushing ? " · 推流中" : ""}`;

export const unitPill = (u) =>
  u.pushing ? ["推流中", "live"] : u.active === "active" ? ["待命", ""] : ["停止", "bad"];

/** 回车提交（md-outlined-text-field 的 keydown 冒泡到宿主）。 */
export const onEnter = (fn) => (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    fn();
  }
};

/** 危险操作二次确认：走 bili-app 里的 md-dialog（焦点陷阱 / Escape 由组件提供）。 */
export function confirmAction(message, confirmText) {
  return document.querySelector("bili-app").confirm(message, confirmText);
}
