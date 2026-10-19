// tasks-view.js — 任务列表（筛选、平台 Chip、按状态分组）。
import { html } from "lit";
import { LightElement } from "../base.js";
import "../components/app-icon.js";
import "../components/task-filters.js";
import "../components/task-list.js";
import { taskState } from "../stores/taskStore.js";
import { appState } from "../stores/appStore.js";
import { overviewState } from "../stores/overviewStore.js";
import { refreshAll } from "../stores/syncStore.js";
import { PLATFORM_ZH, LOGO_COLORS } from "../config/platforms.js";
import { navigate } from "../router.js";
import { openTask, askPause, askResume, askRestart, askDeleteTask } from "../actions/task-actions.js";

const GROUP_META = {
  running: { title: "运行中", color: "var(--brand)" },
  restarting: { title: "重启中", color: "var(--warn)" },
  paused: { title: "已暂停", color: "var(--blue)" },
  failed: { title: "已失败", color: "var(--red)" },
  other: { title: "已停止", color: "var(--muted)" },
};

export class TasksView extends LightElement {
  #onOpen = (event) => openTask(event.detail);
  #onPause = (event) => askPause(event.detail);
  #onResume = (event) => askResume(event.detail);
  #onRestart = (event) => askRestart(event.detail);
  #onDelete = (event) => askDeleteTask(event.detail);

  #platforms() { return Object.entries(overviewState.platforms || {}).sort((a, b) => b[1] - a[1]); }

  #platformNames() { return Object.keys(overviewState.platforms || {}).sort(); }

  #hasFilter() {
    return Boolean(taskState.query.trim() || taskState.stateFilter !== "all" || taskState.liveFilter !== "all" || taskState.platformFilter !== "all");
  }

  #filteredJobs() {
    const query = taskState.query.trim().toLowerCase();
    return taskState.jobs.filter((job) => {
      if (taskState.stateFilter !== "all" && job.state !== taskState.stateFilter) return false;
      if (taskState.liveFilter !== "all" && (job.live || "unknown") !== taskState.liveFilter) return false;
      if (taskState.platformFilter !== "all" && job.platform !== taskState.platformFilter) return false;
      return !query || (job.target + " " + job.platform + " " + job.unit).toLowerCase().includes(query);
    });
  }

  #groups() {
    const buckets = { running: [], restarting: [], paused: [], failed: [], other: [] };
    for (const job of this.#filteredJobs()) {
      // activating（SubState=auto-restart）= 进程已退出、正在重试；单列一组，
      // 避免和真正的"已停止"混在一起（这类行之前还无法停止/移除）。
      switch (job.state) {
        case "active": buckets.running.push(job); break;
        case "activating": buckets.restarting.push(job); break;
        case "paused": buckets.paused.push(job); break;
        case "failed": buckets.failed.push(job); break;
        default: buckets.other.push(job);
      }
    }
    const byTarget = (a, b) => String(a.target || "").localeCompare(String(b.target || ""));
    return ["running", "restarting", "paused", "failed", "other"]
      .map((key) => ({ key, ...GROUP_META[key], jobs: buckets[key].sort(byTarget) }))
      .filter((group) => group.jobs.length);
  }

  #countText() {
    const total = taskState.jobs.length;
    return total ? `${this.#filteredJobs().length}/${total} 个` : "无任务";
  }

  render() {
    const platforms = this.#platforms();
    const groups = this.#groups();
    const hasFilter = this.#hasFilter();
    return html`
      <div class="tasks">
        <section class="panel">
          <div class="panel-title">
            <div class="title-wrap">
              <span class="section-icon"><app-icon name="tasks"></app-icon></span>
              <div><h2>录制任务<span class="count">${this.#countText()}</span></h2><span class="panel-kicker">实时状态与进程控制</span></div>
            </div>
            <task-filters
              .platforms=${this.#platformNames()}
              ?busy=${appState.busy}
              @refresh=${() => refreshAll({ includeFiles: false })}
            ></task-filters>
          </div>
          ${platforms.length
            ? html`<div id="chips" aria-label="平台任务统计">
                ${platforms.map(([platform, count]) => html`
                  <button class="chip ${taskState.platformFilter === platform ? "on" : ""}" type="button" aria-pressed=${String(taskState.platformFilter === platform)} @click=${() => { taskState.platformFilter = platform; }}>
                    ${PLATFORM_ZH[platform] || platform} <b style=${`color:${LOGO_COLORS[platform] || "var(--blue)"}`}>${count}</b>
                  </button>
                `)}
              </div>`
            : ""}
          ${!this.#filteredJobs().length
            ? html`<div class="empty">
                <strong>${hasFilter ? "没有符合条件的任务" : "还没有录制任务"}</strong>
                <span>${hasFilter ? "请调整搜索关键词或筛选条件" : "创建一个任务后，它会显示在这里"}</span>
                ${!hasFilter ? html`<button class="secondary" type="button" @click=${() => navigate("/new")}>新建任务</button>` : ""}
              </div>`
            : ""}
          ${groups.map((group) => html`
            <div class="task-group">
              <h3 class="task-group-title"><span class="gdot" style=${`color:${group.color}`} aria-hidden="true"></span>${group.title}<span class="count">${group.jobs.length}</span></h3>
              <task-list
                .jobs=${group.jobs}
                ?filtered=${true}
                @open=${this.#onOpen}
                @pause=${this.#onPause}
                @resume=${this.#onResume}
                @restart=${this.#onRestart}
                @delete=${this.#onDelete}
              ></task-list>
            </div>
          `)}
        </section>
      </div>
    `;
  }
}

customElements.define("tasks-view", TasksView);
