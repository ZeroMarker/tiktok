// task-filters.js — 任务搜索与筛选工具条（MD3 输入框与下拉框）。
//
// light DOM：`.filter-bar` 应是 .panel-title 的 flex 子项。
import { html } from "lit";
import { LightElement, emit } from "../base.js";
import { taskState } from "../stores/taskStore.js";
import { PLATFORM_ZH } from "../config/platforms.js";
import "../material.js";

const STATES = [
  ["all", "全部状态"],
  ["active", "运行中"],
  ["activating", "重启中"],
  ["paused", "已暂停"],
  ["failed", "失败"],
  ["inactive", "已停止"],
];

const LIVES = [
  ["all", "全部"],
  ["live", "直播中"],
  ["waiting", "等待开播"],
  ["offline", "未开播"],
  ["unknown", "状态未知"],
];

export class TaskFilters extends LightElement {
  static properties = {
    platforms: { type: Array },
    busy: { type: Boolean },
  };

  #hasFilter() {
    return Boolean(taskState.query.trim() || taskState.stateFilter !== "all" || taskState.liveFilter !== "all" || taskState.platformFilter !== "all");
  }

  #clearFilters() {
    taskState.query = "";
    taskState.stateFilter = "all";
    taskState.liveFilter = "all";
    taskState.platformFilter = "all";
  }

  render() {
    return html`
      <div class="filter-bar">
        <md-outlined-text-field
          label="搜索频道或平台"
          .value=${taskState.query}
          @input=${(event) => { taskState.query = event.target.value; }}
        ></md-outlined-text-field>
        <md-outlined-select label="状态" .value=${taskState.stateFilter} @change=${(event) => { taskState.stateFilter = event.target.value; }}>
          ${STATES.map(([value, label]) => html`<md-select-option value=${value}><div slot="headline">${label}</div></md-select-option>`)}
        </md-outlined-select>
        <md-outlined-select label="直播" .value=${taskState.liveFilter} @change=${(event) => { taskState.liveFilter = event.target.value; }}>
          ${LIVES.map(([value, label]) => html`<md-select-option value=${value}><div slot="headline">${label}</div></md-select-option>`)}
        </md-outlined-select>
        <md-outlined-select label="平台" .value=${taskState.platformFilter} @change=${(event) => { taskState.platformFilter = event.target.value; }}>
          <md-select-option value="all"><div slot="headline">全部平台</div></md-select-option>
          ${(this.platforms || []).map((platform) => html`<md-select-option value=${platform}><div slot="headline">${PLATFORM_ZH[platform] || platform}</div></md-select-option>`)}
        </md-outlined-select>
        <md-text-button @click=${() => emit(this, "refresh")} ?disabled=${this.busy}>${this.busy ? "同步中…" : "刷新"}</md-text-button>
        ${this.#hasFilter() ? html`<md-text-button @click=${this.#clearFilters}>清除筛选</md-text-button>` : ""}
      </div>
    `;
  }
}

customElements.define("task-filters", TaskFilters);
