// task-creation-form.js — 新建录制任务表单。
//
// light DOM：`.create-panel .plat-grid` 等规则依赖 NewTask 的 .create-panel 祖先。
// 平台/画质改用 md-filter-chip（单选语义），输入用 md-outlined-text-field。
import { html } from "lit";
import { LightElement } from "../base.js";
import { taskState, startTask } from "../stores/taskStore.js";
import { refreshAll } from "../stores/syncStore.js";
import { navigate } from "../router.js";
import { toast } from "../ui.js";
import { PLATFORM_KEYS, PLATFORM_ZH, PLATFORM_HINTS, QUALITIES, QUALITY_ZH, LOGO_COLORS } from "../config/platforms.js";
import "../material.js";

export class TaskCreationForm extends LightElement {
  static properties = {
    platform: { state: true },
    target: { state: true },
    quality: { state: true },
    submitting: { state: true },
    errorMessage: { state: true },
  };

  constructor() {
    super();
    this.platform = "tiktok";
    this.target = "";
    this.quality = "best";
    this.submitting = false;
    this.errorMessage = "";
  }

  async #onSubmit(event) {
    event.preventDefault();
    this.errorMessage = "";
    const value = this.target.trim();
    if (!value) { toast("请输入频道或直播地址"); return; }
    const duplicate = taskState.jobs.find((job) => job.platform === this.platform && (job.target || "").trim().toLowerCase() === value.toLowerCase());
    if (duplicate) {
      toast(duplicate.state === "paused"
        ? "该频道的录制任务处于暂停状态，请在任务列表中「继续」"
        : "该频道已存在录制任务，请勿重复添加");
      return;
    }
    this.submitting = true;
    try {
      const data = await startTask({ platform: this.platform, target: value, quality: this.quality });
      toast("任务已启动");
      this.target = "";
      taskState.selectedUnit = data.unit;
      await refreshAll({ includeFiles: false });
      navigate("/tasks/" + encodeURIComponent(data.unit));
    } catch (error) {
      this.errorMessage = error.message;
      toast(error.message);
    } finally {
      this.submitting = false;
    }
  }

  render() {
    const hint = PLATFORM_HINTS[this.platform][1];
    return html`
      <form @submit=${this.#onSubmit}>
        <span class="field-label" id="platform-label">平台</span>
        <div class="plat-grid" role="radiogroup" aria-labelledby="platform-label">
          ${PLATFORM_KEYS.map((name) => html`
            <md-filter-chip
              label=${PLATFORM_ZH[name]}
              .selected=${this.platform === name}
              @click=${() => { this.platform = name; }}
              style=${`--md-filter-chip-selected-container-color:color-mix(in srgb, ${LOGO_COLORS[name]} 22%, var(--surf-high)); --md-filter-chip-selected-label-text-color:${LOGO_COLORS[name]}`}
            ></md-filter-chip>
          `)}
        </div>
        <div class="create-grid">
          <md-outlined-text-field
            label="频道或直播地址"
            .value=${this.target}
            required
            aria-describedby="target-hint"
            autocomplete="off"
            @input=${(event) => { this.target = event.target.value; }}
          ></md-outlined-text-field>
          <div>
            <span class="field-label" id="quality-label">录制画质</span>
            <md-chip-set role="radiogroup" aria-labelledby="quality-label">
              ${QUALITIES.map((value) => html`
                <md-filter-chip
                  label=${QUALITY_ZH[value]}
                  .selected=${this.quality === value}
                  @click=${() => { this.quality = value; }}
                ></md-filter-chip>
              `)}
            </md-chip-set>
          </div>
          <md-filled-button type="submit" ?disabled=${this.submitting} aria-busy=${String(this.submitting)}>${this.submitting ? "创建中…" : "开始录制"}</md-filled-button>
        </div>
      </form>
      <div id="platform-hint" class="hint">${hint}</div>
      <div id="target-hint" class="form-help">输入用户名、频道 ID 或完整直播地址。</div>
      ${this.errorMessage ? html`<div class="inline-error" role="alert">${this.errorMessage}</div>` : ""}
    `;
  }
}

customElements.define("task-creation-form", TaskCreationForm);
