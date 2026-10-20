// app-icon.js — 统一图标（light DOM）。
//
// 图标尺寸/颜色由祖先选择器控制（.nav-item .app-icon、.stat-icon .app-icon、
// .section-icon .app-icon、.header-action .app-icon 等），这些规则都在祖先组件
// 的 shadow root 里。因此本组件刻意渲染到 light DOM，让祖先规则能命中 svg。
import { LitElement, html } from "lit";

import { symbols } from "../../vendor/material-symbols/icons.js";

const names = {
  overview: "dashboard",
  tasks: "checklist",
  library: "video_library",
  add: "add",
  record: "radio_button_checked",
  distribution: "bar_chart",
  terminal: "terminal",
  storage: "storage",
  activity: "monitoring",
  refresh: "refresh",
  download: "download",
  circle: "circle",
};

export class AppIcon extends LitElement {
  static properties = { name: { type: String }, filled: { type: Boolean } };

  createRenderRoot() {
    return this;
  }

  render() {
    const symbol = symbols[names[this.name]] || symbols.circle;
    const path = this.filled ? symbol.filled || symbol.outlined : symbol.outlined;
    return html`
      <svg class="app-icon" viewBox="0 -960 960 960" aria-hidden="true" focusable="false">
        <path d=${path}></path>
      </svg>
    `;
  }
}

customElements.define("app-icon", AppIcon);
