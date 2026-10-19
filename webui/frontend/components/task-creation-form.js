// task-creation-form.js — 新建录制任务表单（平台/频道/画质）。
//
// light DOM：`.create-panel .plat-grid` 等规则依赖 NewTask 的 .create-panel 祖先，
// 因此表单内容必须留在同一棵树里（见 styles.js 中的 create-panel 规则）。
import { html } from "lit";
import { LightElement } from "../base.js";
import { taskState, startTask } from "../stores/taskStore.js";
import { refreshAll } from "../stores/syncStore.js";
import { navigate } from "../router.js";
import { toast } from "../ui.js";
import { PLATFORM_KEYS, PLATFORM_ZH, PLATFORM_HINTS, QUALITIES, QUALITY_ZH, LOGO_COLORS } from "../config/platforms.js";

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
      // 暂停中的任务保留在列表里：提示去「继续」，而不是当作重复任务重新创建。
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
    const placeholder = PLATFORM_HINTS[this.platform][0];
    return html`
      <form @submit=${this.#onSubmit}>
        <div class="plat-grid" role="radiogroup" aria-label="平台">
          ${PLATFORM_KEYS.map((name) => html`
            <button
              class="plat-card ${this.platform === name ? "on" : ""}"
              type="button"
              role="radio"
              aria-checked=${String(this.platform === name)}
              style=${`--pc:${LOGO_COLORS[name]}`}
              @click=${() => { this.platform = name; }}
            >
              <span class="pdot" aria-hidden="true"></span>${PLATFORM_ZH[name]}
            </button>
          `)}
        </div>
        <div class="create-grid">
          <div class="field-group field-target">
            <label for="target">频道或直播地址</label>
            <input
              id="target"
              .value=${this.target}
              required
              placeholder=${placeholder}
              aria-describedby="target-hint"
              autocomplete="off"
              @input=${(event) => { this.target = event.target.value; }}
            >
          </div>
          <div class="field-group">
            <span class="field-label" id="quality-label">录制画质</span>
            <div class="seg" role="radiogroup" aria-labelledby="quality-label">
              ${QUALITIES.map((value) => html`
                <button
                  class="seg-btn ${this.quality === value ? "on" : ""}"
                  type="button"
                  role="radio"
                  aria-checked=${String(this.quality === value)}
                  @click=${() => { this.quality = value; }}
                >${QUALITY_ZH[value]}</button>
              `)}
            </div>
          </div>
          <button type="submit" ?disabled=${this.submitting} aria-busy=${String(this.submitting)}>${this.submitting ? "创建中…" : "开始录制"}</button>
        </div>
      </form>
      <div id="platform-hint" class="hint">${hint}</div>
      <div id="target-hint" class="form-help">输入用户名、频道 ID 或完整直播地址。</div>
      ${this.errorMessage ? html`<div class="inline-error" role="alert">${this.errorMessage}</div>` : ""}
    `;
  }
}

customElements.define("task-creation-form", TaskCreationForm);
