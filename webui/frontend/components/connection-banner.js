// connection-banner.js — 连接状态行 + 部分同步失败提示。
import { html, css } from "lit";
import { BaseElement } from "../base.js";
import { appState } from "../stores/appStore.js";
import { refreshAll } from "../stores/syncStore.js";
import "../material.js";

export class ConnectionBanner extends BaseElement {
  // 两个顶层节点位于 .page-content 里；host 用普通块级盒即可。
  static styles = [...BaseElement.styles, css`:host { display: block; }`];

  #statusText() {
    if (appState.offline) return appState.loadedOnce ? "离线模式 · 显示缓存" : "离线模式 · 等待连接";
    if (appState.degraded) return "部分数据同步失败";
    return appState.lastSynced ? "已同步 " + new Date(appState.lastSynced).toLocaleTimeString() : "等待同步";
  }

  render() {
    const hasErrors = Object.values(appState.errors).some(Boolean);
    return html`
      <div class="statusline ${appState.degraded || appState.offline ? "warn" : ""}" role="status" aria-live="polite">
        <span>${this.#statusText()}</span>
        ${appState.degraded ? html`<span class="b-bad">服务异常</span>` : ""}
        ${appState.degraded || appState.offline
          ? html`<md-text-button compact @click=${refreshAll}>重试</md-text-button>`
          : ""}
      </div>
      ${hasErrors
        ? html`<div class="error-banner" role="alert">
            <span>部分数据暂时不可用：</span>
            ${appState.errors.jobs ? html`<span>任务</span>` : ""}
            ${appState.errors.overview ? html`<span>概览</span>` : ""}
            ${appState.errors.files ? html`<span>文件</span>` : ""}
            <md-text-button compact @click=${refreshAll}>重新同步</md-text-button>
          </div>`
        : ""}
    `;
  }
}

customElements.define("connection-banner", ConnectionBanner);
