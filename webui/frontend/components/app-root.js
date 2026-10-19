// app-root.js — 应用外壳：顶部栏 + 导航 + 视图切换 + 全局反馈。
import { html, css } from "lit";
import { BaseElement } from "../base.js";
import { appState } from "../stores/appStore.js";
import { route } from "../router.js";
import "./app-header.js";
import "./app-nav.js";
import "./connection-banner.js";
import "./global-feedback.js";
import "../views/overview-view.js";
import "../views/tasks-view.js";
import "../views/task-detail-view.js";
import "../views/library-view.js";
import "../views/new-task-view.js";

export class AppRoot extends BaseElement {
  static styles = [...BaseElement.styles, css`:host { display: block; }`];

  #skip(event) {
    event.preventDefault();
    this.renderRoot.querySelector("#page-content")?.focus();
  }

  #view() {
    switch (route.name) {
      case "tasks": return html`<tasks-view></tasks-view>`;
      case "task": return html`<task-detail-view unit=${route.unit}></task-detail-view>`;
      case "library": return html`<library-view></library-view>`;
      case "new": return html`<new-task-view></new-task-view>`;
      default: return html`<overview-view></overview-view>`;
    }
  }

  render() {
    return html`
      <div class="shell ${appState.offline ? "offline" : ""} ${appState.degraded ? "degraded" : ""}">
        <app-header></app-header>
        <a class="skip-link" href="#page-content" @click=${this.#skip}>跳转到页面内容</a>
        <div class="workspace">
          <app-nav></app-nav>
          <main id="page-content" class="page-content" tabindex="-1">
            <connection-banner></connection-banner>
            ${appState.busy && !appState.loadedOnce
              ? html`<div class="loading-state" role="status">正在同步直播任务与录制文件…</div>`
              : this.#view()}
          </main>
        </div>
        <global-feedback></global-feedback>
      </div>
    `;
  }
}

customElements.define("app-root", AppRoot);
