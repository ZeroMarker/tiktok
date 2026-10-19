// metric-card.js — 概览指标卡。
//
// light DOM：`.stat` 必须是 .stats 网格的直接子项，且第 1..4 张卡的位置配色在
// styles.js 里以 `metric-card:nth-child(n) .stat…` 表达（DOM 里四个 metric-card
// 就是 .stats 的兄弟节点）。bar 自身的阈值配色仍走内联样式（原实现如此）。
import { html } from "lit";
import { LightElement } from "../base.js";
import "./app-icon.js";

export class MetricCard extends LightElement {
  static properties = {
    label: { type: String },
    icon: { type: String },
    value: { type: String },
    note: { type: String },
    bar: { type: Number },
  };

  render() {
    const bar = this.bar;
    const tone = bar == null ? "" : bar >= 90 ? "var(--red)" : bar >= 75 ? "var(--warn)" : "";
    const clamp = Math.min(100, Math.max(0, bar ?? 0));
    return html`
      <div class="stat">
        <div class="stat-top">
          <span class="stat-label">${this.label}</span>
          <span class="stat-icon"><app-icon name=${this.icon}></app-icon></span>
        </div>
        <b style=${bar != null ? `color:${tone}` : ""}>${this.value}</b>
        <span class="stat-note">${this.note}</span>
        ${bar != null
          ? html`<div class="bar" aria-hidden="true"><i style=${`width:${clamp}%;background:${tone || "linear-gradient(90deg,var(--brand),var(--blue))"}`}></i></div>`
          : ""}
      </div>
    `;
  }
}

customElements.define("metric-card", MetricCard);
