// app-nav.js — 主导航（Material list）。
//
// light DOM：`.nav` 是 .workspace 网格里的 sticky 列，必须保持“网格项 = .nav”。
import { html } from "lit";
import { LightElement } from "../base.js";
import { route, navigate } from "../router.js";
import "../material.js";
import "./app-icon.js";

const ITEMS = [
  { path: "/", label: "概览", name: "overview", icon: "overview" },
  { path: "/tasks", label: "任务", name: "tasks", icon: "tasks" },
  { path: "/library", label: "录制文件", name: "library", icon: "library" },
  { path: "/new", label: "新建任务", name: "new", icon: "add" },
];

export class AppNav extends LightElement {
  #isActive(item) {
    return route.name === item.name || (item.name === "tasks" && route.name === "task");
  }

  render() {
    return html`
      <nav class="nav" aria-label="主导航">
        <p class="nav-label">工作空间</p>
        <md-list>
          ${ITEMS.map((item) => {
            const active = this.#isActive(item);
            return html`
              <md-list-item
                type="button"
                ?active=${active}
                aria-current=${active ? "page" : undefined}
                @click=${() => navigate(item.path)}
              >
                <app-icon slot="start" name=${item.icon}></app-icon>
                <div slot="headline">${item.label}</div>
              </md-list-item>
            `;
          })}
        </md-list>
        <div class="nav-note"><app-icon name="record"></app-icon><span>跨平台录制<br><small>统一管理每一场直播</small></span></div>
      </nav>
    `;
  }
}

customElements.define("app-nav", AppNav);
