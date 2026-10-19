// log-panel.js — 任务日志面板（自动刷新、换行、只显示错误、复制）。
import { html, css } from "lit";
import { BaseElement } from "../base.js";
import { fetchTaskLogs } from "../stores/taskStore.js";
import { toast } from "../ui.js";

const TAILS = ["200", "1000", "5000"];

export class LogPanel extends BaseElement {
  static properties = {
    unit: { type: String },
    rawLines: { state: true },
    autoLog: { state: true },
    tail: { state: true },
    wrap: { state: true },
    errorsOnly: { state: true },
    loading: { state: true },
    error: { state: true },
  };

  static styles = [...BaseElement.styles, css`:host { display: block; }`];

  #timer = null;
  #requestId = 0;

  constructor() {
    super();
    this.unit = "";
    this.rawLines = [];
    this.autoLog = true;
    this.tail = "200";
    this.wrap = true;
    this.errorsOnly = false;
    this.loading = false;
    this.error = "";
  }

  connectedCallback() {
    super.connectedCallback();
    this.#timer = setInterval(() => { if (this.autoLog) this.#fetchLogs(); }, 5000);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearInterval(this.#timer);
    this.#timer = null;
  }

  updated(changed) {
    if (changed.has("unit") || changed.has("tail")) this.#fetchLogs();
    if (changed.has("rawLines")) {
      const pre = this.renderRoot.querySelector("pre");
      if (pre) pre.scrollTop = pre.scrollHeight;
    }
  }

  #displayed() {
    const lines = this.errorsOnly ? this.rawLines.filter((line) => /error|fail|exception|panic|ERR/i.test(line)) : this.rawLines;
    return lines.join("\n");
  }

  async #fetchLogs() {
    const current = ++this.#requestId;
    this.loading = true;
    this.error = "";
    try {
      const text = await fetchTaskLogs(this.unit, Number(this.tail));
      if (current !== this.#requestId) return;
      this.rawLines = text.split("\n");
    } catch (reason) {
      if (current === this.#requestId) this.error = reason.message || "日志加载失败";
    } finally {
      if (current === this.#requestId) this.loading = false;
    }
  }

  #clear() {
    this.rawLines = [];
    toast("日志已清屏，自动刷新后会重新显示");
  }

  async #copy() {
    try {
      if (!navigator.clipboard) throw new Error("clipboard unavailable");
      await navigator.clipboard.writeText(this.#displayed());
      toast("日志已复制");
    } catch { toast("复制失败，请手动选择文本"); }
  }

  render() {
    return html`
      <div class="log-console">
        <div class="log-tools">
          <label><input type="checkbox" .checked=${this.autoLog} @change=${(event) => { this.autoLog = event.target.checked; }}> 自动刷新</label>
          <select aria-label="日志行数" @change=${(event) => { this.tail = event.target.value; }}>
            ${TAILS.map((value) => html`<option value=${value} ?selected=${this.tail === value}>${value} 行</option>`)}
          </select>
          <button class="mini secondary" type="button" @click=${() => { this.wrap = !this.wrap; }}>${this.wrap ? "关闭换行" : "开启换行"}</button>
          <button class="mini secondary" type="button" @click=${() => { this.errorsOnly = !this.errorsOnly; }}>${this.errorsOnly ? "全部日志" : "只显示错误"}</button>
          <button class="mini secondary" type="button" @click=${this.#clear}>清屏</button>
          <button class="mini secondary" type="button" @click=${this.#copy}>复制日志</button>
        </div>
        ${this.loading
          ? html`<div class="loading-state" role="status">正在加载日志…</div>`
          : this.error
            ? html`<div class="error-state" role="alert">${this.error}</div>`
            : html`<pre class="logs ${this.wrap ? "" : "nowrap"}">${this.#displayed() || "暂无日志"}</pre>`}
      </div>
    `;
  }
}

customElements.define("log-panel", LogPanel);
