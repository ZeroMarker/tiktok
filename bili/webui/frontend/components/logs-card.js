// <logs-card> — 服务日志（journalctl）与「停止全部推流」。
import { html, nothing } from "lit";
import * as api from "../api.js";
import { fail, notify, run } from "../actions.js";
import { BaseElement } from "../base.js";
import { state } from "../store.js";
import { cardHead, confirmAction, spinner, spinning } from "../ui.js";

const SERVICES = [["live", "直播推流"], ["replay", "文件轮播"], ["monitor", "值守"], ["webui", "webui"]];
const TAILS = ["100", "300", "600"];

class LogsCard extends BaseElement {
  static properties = {
    which: { state: true }, tail: { state: true }, auto: { state: true }, logs: { state: true },
  };

  #timer = null;

  constructor() {
    super();
    this.which = "live";
    this.tail = "300";
    this.auto = false;
    this.logs = null; // null = 还没打开过
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearInterval(this.#timer);
  }

  async #load(background = false) {
    try {
      const r = await api.fetchLogs(this.which, this.tail);
      const pre = this.querySelector("pre");
      // 贴底时自动跟随新日志；手动往上翻时不打断阅读
      const stick = !pre || pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 40;
      this.logs = r.logs || "(空)";
      await this.updateComplete;
      if (stick) {
        const out = this.querySelector("pre");
        out.scrollTop = out.scrollHeight;
      }
    } catch (e) {
      if (!background) fail(e);
    }
  }

  #view() {
    run("logs", () => this.#load(), { reload: false });
  }

  #select(key) {
    return (e) => {
      this[key] = e.target.value;
      if (this.logs !== null) this.#load(true); // 已打开则立即跟着刷新
    };
  }

  #toggleAuto(e) {
    this.auto = e.target.checked;
    clearInterval(this.#timer);
    this.#timer = null;
    if (this.auto) {
      this.#load(true);
      this.#timer = setInterval(() => { if (!document.hidden) this.#load(true); }, 5000);
    }
  }

  async #copy() {
    try {
      await navigator.clipboard.writeText(this.logs);
      notify("日志已复制");
    } catch (e) {
      fail(new Error("复制失败：" + e.message));
    }
  }

  async #stopAll() {
    if (!(await confirmAction(
      "停止全部推流？直播推流和文件轮播都会停掉，值守同时关闭（之后开播也不会自动起流），B 站房间保持当前开播状态。",
      "停止全部"))) return;
    run("stopAll", async () => {
      await api.post("/api/stop");
      return "已停止全部推流并关闭值守，房间开播状态保持原样";
    });
  }

  render() {
    const busy = !!state.busy;
    return html`<section class="card">
      ${cardHead("logs", "服务日志", "查看最近运行记录或停止全部推流")}
      <div class="row">
        <md-outlined-select class="narrow" label="服务" .value=${this.which} ?disabled=${busy}
            @change=${this.#select("which")}>
          ${SERVICES.map(([v, label]) => html`<md-select-option value=${v} ?selected=${v === this.which}>
            <div slot="headline">${label}</div></md-select-option>`)}
        </md-outlined-select>
        <md-outlined-select class="narrow" label="行数" .value=${this.tail} ?disabled=${busy}
            @change=${this.#select("tail")}>
          ${TAILS.map((v) => html`<md-select-option value=${v} ?selected=${v === this.tail}>
            <div slot="headline">${v} 行</div></md-select-option>`)}
        </md-outlined-select>
        <md-filled-button class="tonal" ?has-icon=${spinning("logs")} ?disabled=${busy}
            @click=${() => this.#view()}>${spinner("logs")}查看</md-filled-button>
        <label class="check"><md-checkbox touch-target="wrapper" ?checked=${this.auto} ?disabled=${busy}
            @change=${(e) => this.#toggleAuto(e)}></md-checkbox>每 5 秒自动刷新</label>
        <div class="spacer"></div>
        ${this.logs !== null
          ? html`<md-outlined-button ?disabled=${busy} @click=${() => this.#copy()}>复制</md-outlined-button>`
          : nothing}
        <md-filled-button class="danger" ?has-icon=${spinning("stopAll")} ?disabled=${busy}
            @click=${() => this.#stopAll()}>${spinner("stopAll")}停止全部推流</md-filled-button>
      </div>
      ${this.logs !== null ? html`<pre>${this.logs}</pre>` : nothing}
    </section>`;
  }
}
customElements.define("logs-card", LogsCard);
