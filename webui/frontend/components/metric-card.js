// metric-card.js — 概览指标卡。
//
// light DOM：`.stat` 必须是 .stats 网格的直接子项；位置配色用 metric-card:nth-child。
// 进度条改用 md-linear-progress。
import { html } from "lit";
import { LightElement } from "../base.js";
import "../material.js";
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
    const clamp = Math.min(100, Math.max(0, bar ?? 0));
    return html`
      <div class="stat">
        <div class="stat-top">
          <span class="stat-label">${this.label}</span>
          <span class="stat-icon"><app-icon name=${this.icon}></app-icon></span>
        </div>
        <b>${this.value}</b>
        <span class="stat-note">${this.note}</span>
        ${bar != null
          ? html`<md-linear-progress .value=${clamp / 100} aria-label=${this.label}></md-linear-progress>`
          : ""}
      </div>
    `;
  }
}

customElements.define("metric-card", MetricCard);
