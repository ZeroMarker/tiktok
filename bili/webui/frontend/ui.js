// ui.js — 共用渲染片段：图标、按钮转圈、单元状态文案、确认对话框。
import { html, nothing, svg } from "lit";
import { state } from "./store.js";

import { symbols } from "../vendor/material-symbols/icons.js";

const ICONS = {
  logo: "videocam",
  refresh: "refresh",
  status: "play_circle",
  live: "live_tv",
  replay: "video_library",
  room: "home",
  logs: "article",
};

export const icon = (name, size = 20) =>
  html`<svg width=${size} height=${size} viewBox="0 -960 960 960" fill="currentColor" aria-hidden="true" focusable="false">${svg`<path d=${(symbols[ICONS[name]] || symbols.videocam).outlined}></path>`}</svg>`;

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
