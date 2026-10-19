// task-filters.js — 任务搜索与筛选工具条。
//
// light DOM：`.filter-bar` 应是 .panel-title 的 flex 子项。
import { html } from "lit";
import { LightElement, emit } from "../base.js";
import { taskState } from "../stores/taskStore.js";
import { PLATFORM_ZH } from "../config/platforms.js";

const STATES = [
  ["all", "全部状态"],
  ["active", "运行中"],
  ["activating", "重启中"],
  ["paused", "已暂停"],
  ["failed", "失败"],
  ["inactive", "已停止"],
];

const LIVES = [
  ["all", "全部直播状态"],
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
        <input
          placeholder="搜索频道或平台"
          aria-label="搜索任务"
          .value=${taskState.query}
          @input=${(event) => { taskState.query = event.target.value; }}
        >
        <select aria-label="状态筛选" @change=${(event) => { taskState.stateFilter = event.target.value; }}>
          ${STATES.map(([value, label]) => html`<option value=${value} ?selected=${taskState.stateFilter === value}>${label}</option>`)}
        </select>
        <select aria-label="直播状态筛选" @change=${(event) => { taskState.liveFilter = event.target.value; }}>
          ${LIVES.map(([value, label]) => html`<option value=${value} ?selected=${taskState.liveFilter === value}>${label}</option>`)}
        </select>
        <select aria-label="平台筛选" @change=${(event) => { taskState.platformFilter = event.target.value; }}>
          <option value="all" ?selected=${taskState.platformFilter === "all"}>全部平台</option>
          ${(this.platforms || []).map((platform) => html`<option value=${platform} ?selected=${taskState.platformFilter === platform}>${PLATFORM_ZH[platform] || platform}</option>`)}
        </select>
        <button class="secondary" type="button" ?disabled=${this.busy} @click=${() => emit(this, "refresh")}>${this.busy ? "同步中…" : "刷新"}</button>
        ${this.#hasFilter() ? html`<button class="text-button" type="button" @click=${this.#clearFilters}>清除筛选</button>` : ""}
      </div>
    `;
  }
}

customElements.define("task-filters", TaskFilters);
