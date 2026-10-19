// task-card.js — 单个录制任务卡片（状态、事实、控制动作）。
//
// light DOM：`.job` 必须是 .jobs 网格的直接子项。
// 动作按钮使用 MD3：次要动作为 md-text-button，危险动作为带 .danger 的 md-text-button。
import { html } from "lit";
import { LightElement, emit } from "../base.js";
import { PLATFORM_ZH, LOGO_COLORS, stateClass, stateLabel, liveClass, liveLabel, isStopping, isPaused, fmtBytes, fmtUptime } from "../utils.js";
import { toast } from "../ui.js";
import { taskState } from "../stores/taskStore.js";
import "../material.js";

export class TaskCard extends LightElement {
  static properties = {
    job: { type: Object },
    selected: { type: Boolean },
  };

  #pending() { return taskState.pendingUnit === this.job.unit; }
  #stopping() { return isStopping(this.job); }
  #paused() { return isPaused(this.job); }
  #busy() { return this.#pending() || this.#stopping(); }
  #canPause() { return this.job.state !== "inactive" && this.job.state !== "failed"; }

  async #copy() {
    try {
      if (navigator.clipboard && window.isSecureContext) {
        await navigator.clipboard.writeText(this.job.unit);
      } else {
        const input = document.createElement("textarea");
        input.value = this.job.unit;
        input.style.position = "fixed";
        input.style.opacity = "0";
        document.body.appendChild(input);
        input.select();
        if (!document.execCommand("copy")) throw new Error("copy failed");
        input.remove();
      }
      toast("任务名称已复制");
    } catch { toast("复制失败，请手动选择文本"); }
  }

  render() {
    const job = this.job;
    const platformZh = PLATFORM_ZH[job.platform] || job.platform || "—";
    const logoColor = LOGO_COLORS[job.platform] || "var(--blue)";
    const pending = this.#pending();
    const stopping = this.#stopping();
    const paused = this.#paused();
    const busy = pending || stopping;
    const action = taskState.pendingAction;
    return html`
      <article
        class="job ${this.selected ? "sel" : ""}"
        data-state=${job.state}
        data-live=${job.live || "unknown"}
        style=${`--pc:${logoColor}`}
      >
        <div class="logo" style=${`color:${logoColor}`}>${(job.platform || "?").slice(0, 2)}</div>
        <div class="job-main">
          <div class="job-heading">
            <button class="job-title" type="button" title=${job.target} @click=${() => emit(this, "open", job)}>${job.target}</button>
            <span class="platform-tag">${platformZh}</span>
          </div>
          <div class="job-facts">
            <span class="status ${stateClass(job.state, job.substate)}">${stateLabel(job.state, job.substate)}</span>
            <span class="status ${liveClass(job.live)}">${liveLabel(job.live)}</span>
            ${!paused ? html`<span>PID ${job.pid || "—"}</span>` : ""}
            ${!paused ? html`<span>内存 ${fmtBytes(job.memory)}</span>` : ""}
            ${job.restarts ? html`<span>重启 ${job.restarts}</span>` : ""}
            ${job.state === "active" ? html`<span>已运行 ${fmtUptime(job.started)}</span>` : ""}
          </div>
        </div>
        <div class="actions">
          <md-text-button compact @click=${() => emit(this, "open", job)} ?disabled=${busy}>日志</md-text-button>
          <md-text-button compact @click=${this.#copy} ?disabled=${busy}>复制名称</md-text-button>
          ${paused
            ? html`<md-outlined-button compact @click=${() => emit(this, "resume", job)} ?disabled=${busy}>${pending && action === "resume" ? "继续中…" : "继续"}</md-outlined-button>`
            : html`
                <md-text-button compact @click=${() => emit(this, "pause", job)} ?disabled=${busy || !this.#canPause()}>${stopping || (pending && action === "pause") ? "暂停中…" : "暂停"}</md-text-button>
                <md-text-button compact @click=${() => emit(this, "restart", job)} ?disabled=${busy}>${pending && action === "restart" ? "重启中…" : "重启"}</md-text-button>
              `}
          <md-text-button class="danger" compact @click=${() => emit(this, "delete", job)} ?disabled=${busy}>${pending && action === "delete" ? "删除中…" : "删除"}</md-text-button>
        </div>
      </article>
    `;
  }
}

customElements.define("task-card", TaskCard);
