// task-list.js — 任务卡片列表。
//
// light DOM：`.jobs` 网格应保持在使用方容器里。
// 卡片事件（bubbles + composed）会直接冒泡到使用方，无需在此中转。
import { html } from "lit";
import { LightElement } from "../base.js";
import { taskState } from "../stores/taskStore.js";
import { navigate } from "../router.js";
import "./task-card.js";

export class TaskList extends LightElement {
  static properties = {
    jobs: { type: Array },
    filtered: { type: Boolean },
  };

  render() {
    const jobs = this.jobs || [];
    return html`
      <div class="jobs">
        ${jobs.map((job) => html`
          <task-card .job=${job} ?selected=${job.unit === taskState.selectedUnit}></task-card>
        `)}
        ${!jobs.length
          ? html`<div class="empty">
              <strong>${this.filtered ? "没有符合条件的任务" : "还没有录制任务"}</strong>
              <span>${this.filtered ? "请调整搜索关键词或筛选条件" : "创建一个任务后，它会显示在这里"}</span>
              ${!this.filtered ? html`<button class="secondary" type="button" @click=${() => navigate("/new")}>新建任务</button>` : ""}
            </div>`
          : ""}
      </div>
    `;
  }
}

customElements.define("task-list", TaskList);
