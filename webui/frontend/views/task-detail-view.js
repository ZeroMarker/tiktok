// task-detail-view.js — 任务详情与控制。
import { html } from "lit";
import { LightElement } from "../base.js";
import "../material.js";
import "../components/app-icon.js";
import "../components/log-panel.js";
import { taskState } from "../stores/taskStore.js";
import { PLATFORM_ZH, QUALITY_ZH, stateLabel, liveClass, liveLabel, isStopping, isPaused, fmtBytes, fmtUptime } from "../utils.js";
import { navigate } from "../router.js";
import { askPause, askResume, askRestart, askDeleteTask } from "../actions/task-actions.js";

export class TaskDetailView extends LightElement {
  static properties = { unit: { type: String } };

  #onPause = () => askPause(this.#job());
  #onResume = () => askResume(this.#job());
  #onRestart = () => askRestart(this.#job());
  #onDelete = () => askDeleteTask(this.#job(), () => navigate("/tasks"));

  #job() { return taskState.jobs.find((job) => job.unit === this.unit); }

  #pending() { return taskState.pendingUnit === this.unit; }

  // 与任务卡片一致：正在收尾（deactivating）或请求在途都算"暂停中"。
  #stopping() { return isStopping(this.#job()); }

  #paused() { return isPaused(this.#job()); }

  #busy() { return this.#pending() || this.#stopping(); }

  // 只有运行中的任务可以暂停；已停止/失败的任务直接删除即可。
  #canPause() {
    const job = this.#job();
    return Boolean(job) && job.state !== "inactive" && job.state !== "failed";
  }

  #startedText() {
    const job = this.#job();
    if (!job) return "启动时间未知";
    if (this.#paused()) return "已暂停";
    if (job.state === "active") return "已运行 " + fmtUptime(job.started);
    return job.started ? new Date(job.started).toLocaleString() : "启动时间未知";
  }

  render() {
    const job = this.#job();
    const pending = this.#pending();
    const stopping = this.#stopping();
    const paused = this.#paused();
    const busy = this.#busy();
    const action = taskState.pendingAction;
    return html`
      <div class="task-detail">
        ${!job
          ? html`<section class="panel">
              <div class="panel-title">
                <div class="title-wrap">
                  <span class="section-icon"><app-icon name="tasks"></app-icon></span>
                  <div><h2>任务详情</h2><span class="panel-kicker">${this.unit}</span></div>
                </div>
                <div class="actions"><md-text-button @click=${() => navigate("/tasks")}>返回任务</md-text-button></div>
              </div>
              <div class="hint warn">该任务当前不在 systemd 单元列表中（可能已移除），仍可查看最近日志。</div>
            </section>`
          : ""}
        <div class="split">
          ${job
            ? html`<section class="panel">
                <div class="panel-title">
                  <div class="title-wrap">
                    <span class="section-icon"><app-icon name="tasks"></app-icon></span>
                    <div>
                      <h2>${job.target}<span class="platform-tag">${PLATFORM_ZH[job.platform] || job.platform}</span></h2>
                      <span class="panel-kicker">${stateLabel(job.state, job.substate)}</span>
                    </div>
                  </div>
                </div>
                <dl class="kv">
                  <dt>状态</dt><dd>${stateLabel(job.state, job.substate)}</dd>
                  <dt>直播</dt><dd class=${liveClass(job.live)}>${liveLabel(job.live)}</dd>
                  <dt>平台</dt><dd>${PLATFORM_ZH[job.platform] || job.platform}</dd>
                  ${paused
                    ? html`<dt>画质</dt><dd>${QUALITY_ZH[job.quality] || job.quality || "原画"}</dd>`
                    : html`<dt>进程</dt><dd>PID ${job.pid || "—"} · 内存 ${fmtBytes(job.memory)}</dd>`}
                  <dt>运行时长</dt><dd>${this.#startedText()}</dd>
                  <dt>单元</dt><dd class="wrap">${job.unit}</dd>
                </dl>
                <div class="detail-actions">
                  <md-text-button @click=${() => navigate("/tasks")}>返回任务</md-text-button>
                  ${paused
                    ? html`<md-outlined-button ?disabled=${busy} @click=${this.#onResume}>${pending && action === "resume" ? "继续中…" : "继续"}</md-outlined-button>`
                    : html`
                        <md-text-button ?disabled=${busy || !this.#canPause()} @click=${this.#onPause}>${stopping || (pending && action === "pause") ? "暂停中…" : "暂停"}</md-text-button>
                        <md-text-button ?disabled=${busy} @click=${this.#onRestart}>${pending && action === "restart" ? "重启中…" : "重启"}</md-text-button>
                      `}
                  <md-text-button class="danger" ?disabled=${busy} @click=${this.#onDelete}>${pending && action === "delete" ? "删除中…" : "删除"}</md-text-button>
                </div>
              </section>`
            : ""}
          <section class="panel">
            <div class="panel-title">
              <div class="title-wrap">
                <span class="section-icon"><app-icon name="terminal"></app-icon></span>
                <div><h2>任务日志</h2><span class="panel-kicker">Journal 实时输出</span></div>
              </div>
              <md-text-button @click=${() => navigate("/library")}>录制文件</md-text-button>
            </div>
            <log-panel unit=${this.unit}></log-panel>
          </section>
        </div>
      </div>
    `;
  }
}

customElements.define("task-detail-view", TaskDetailView);
