// app-header.js — 顶部状态栏（连接状态、时钟、安装、刷新）。
//
// light DOM：`.topbar` 是 sticky，必须是 .shell 的直接流子元素。
// 控件使用 @material/web（md-outlined-button / md-text-button）。
import { html } from "lit";
import { LightElement } from "../base.js";
import { appState } from "../stores/appStore.js";
import { refreshAll } from "../stores/syncStore.js";
import "../material.js";
import "./app-icon.js";

export class AppHeader extends LightElement {
  static properties = { clock: { state: true } };

  #clockTimer = null;

  constructor() {
    super();
    this.clock = "";
  }

  #captureInstallPrompt = (event) => {
    event.preventDefault();
    appState.installPrompt = event;
  };

  connectedCallback() {
    super.connectedCallback();
    this.clock = new Date().toLocaleTimeString();
    this.#clockTimer = setInterval(() => { this.clock = new Date().toLocaleTimeString(); }, 1000);
    window.addEventListener("beforeinstallprompt", this.#captureInstallPrompt);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearInterval(this.#clockTimer);
    this.#clockTimer = null;
    window.removeEventListener("beforeinstallprompt", this.#captureInstallPrompt);
  }

  async #install() {
    if (!appState.installPrompt) return;
    appState.installPrompt.prompt();
    await appState.installPrompt.userChoice;
    appState.installPrompt = null;
  }

  #connectionText() {
    return appState.offline ? "离线" : appState.degraded ? "服务异常" : "服务在线";
  }

  #statusText() {
    if (appState.offline) return appState.loadedOnce ? "离线模式 · 显示缓存" : "离线模式 · 等待连接";
    if (appState.degraded) return "部分数据同步失败";
    return appState.lastSynced ? "已同步 " + new Date(appState.lastSynced).toLocaleTimeString() : "等待同步";
  }

  render() {
    return html`
      <header class="topbar">
        <div class="brand">
          <div class="brand-mark" aria-hidden="true"></div>
          <div><p class="eyebrow">Live Control</p><h1>直播录制中心</h1><p class="sub">聚合管理跨平台录制任务</p></div>
        </div>
        <div class="head-right">
          <div class="status-pill" title=${this.#statusText()}><div class="online"><i class="dot" aria-hidden="true"></i><span>${this.#connectionText()}</span></div></div>
          <div class="clock-pill" title=${`本地时间 ${this.clock}`}><span>${this.clock}</span></div>
          ${appState.installPrompt
            ? html`<md-text-button @click=${this.#install}><app-icon slot="icon" name="download"></app-icon>安装应用</md-text-button>`
            : ""}
          <md-outlined-button @click=${refreshAll} ?disabled=${appState.busy} aria-busy=${String(appState.busy)}>
            <app-icon slot="icon" name="refresh" class=${appState.busy ? "spinning" : ""}></app-icon>
            ${appState.busy ? "同步中…" : "刷新"}
          </md-outlined-button>
        </div>
      </header>
    `;
  }
}

customElements.define("app-header", AppHeader);
