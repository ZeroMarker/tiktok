// <live-card> — 直播推流：固定目标主播、立即检测、值守开关。
import { html } from "lit";
import { live } from "lit/directives/live.js";
import * as api from "../api.js";
import { fail, notify, refresh, run } from "../actions.js";
import { BaseElement, loadDraft, saveDraft } from "../base.js";
import { set, state } from "../store.js";
import { cardHead, onEnter, spinner, spinning } from "../ui.js";

class LiveCard extends BaseElement {
  static properties = { target: { state: true }, force: { state: true } };

  constructor() {
    super();
    this.target = loadDraft().target || "";
    this.force = false;
  }

  willUpdate() {
    // 后端状态才是准的：只填空，不覆盖用户正在输入的目标
    const fixed = state.status?.target?.target;
    if (fixed && !this.target.trim()) this.target = fixed;
  }

  #start() {
    const target = this.target.trim();
    if (!target) return fail(new Error("请填写 TikTok 用户名"));
    saveDraft({ target });
    run("live", async () => {
      notify(this.force ? "跳过验流，直接切换（空等复播）…"
                        : `正在验证 @${target} 的直播流（≤45s），拿到地址才切换…`);
      await api.post("/api/mode", { mode: "live", target, force: this.force });
      return "已切换到直播推流";
    });
  }

  #probe() {
    const who = this.target.trim();
    if (!who) return fail(new Error("未设置目标主播，请先填写"));
    run("probe", async () => {
      notify(`正在检测 @${who} 是否开播（抓流最多 2 分钟）…`);
      await api.post("/api/probe");
      return "检测完成";
    });
  }

  #watch(e) {
    const enabled = e.target.checked;
    run("arm", async () => {
      try {
        await api.post("/api/arm", { enabled });
      } catch (err) {
        await refresh(); // 回滚复选框到后端真实状态
        throw err;
      }
      return enabled ? "值守已开启：开播自动起推流、关播自动停推流" : "值守已关闭：之后开播也不会自动起推流";
    });
  }

  #subtitles(e) {
    const enabled = e.target.checked;
    run("subtitles", async () => {
      const result = await api.post("/api/subtitles", { enabled });
      set({ status: { ...state.status, subtitles: result.subtitles } });
      return `直播字幕已${enabled ? "开启" : "关闭"}${result.restarted ? "，推流已重启" : "，下次直播推流时生效"}`;
    });
  }

  render() {
    const busy = !!state.busy;
    const armed = !!state.status?.target?.armed;
    const subtitles = state.status?.subtitles || {};
    return html`<section class="card">
      ${cardHead("live", "直播推流", "固定一个 TikTok 主播，开播自动转推、关播自动停推", "LIVE")}
      <div class="row">
        <md-outlined-text-field label="固定目标主播（TikTok 用户名，换人改这里）" placeholder="如 ayakiguchi1"
            autocapitalize="none" spellcheck="false" .value=${this.target} ?disabled=${busy}
            @input=${(e) => { this.target = e.target.value; saveDraft({ target: this.target }); }}
            @keydown=${onEnter(() => this.#start())}></md-outlined-text-field>
        <md-filled-button ?has-icon=${spinning("live")} ?disabled=${busy} @click=${() => this.#start()}>
          ${spinner("live")}设为目标并启动</md-filled-button>
        <md-filled-button class="tonal" ?has-icon=${spinning("probe")} ?disabled=${busy}
            @click=${() => this.#probe()}>${spinner("probe")}立即检测</md-filled-button>
      </div>
      <div class="row">
        <label class="check"><md-checkbox touch-target="wrapper" ?checked=${this.force} ?disabled=${busy}
            @change=${(e) => { this.force = e.target.checked; }}></md-checkbox>没开播也切换（空等复播）</label>
        <label class="check"><md-checkbox touch-target="wrapper" .checked=${live(armed)} ?disabled=${busy}
            @change=${(e) => this.#watch(e)}></md-checkbox>值守：开播自动起推流、关播自动停推流</label>
      </div>
      <div class="row">
        <label class="check"><md-checkbox touch-target="wrapper" .checked=${live(!!subtitles.enabled)}
            ?disabled=${busy || !state.status || (!subtitles.ready && !subtitles.enabled)}
            @change=${(e) => this.#subtitles(e)}></md-checkbox>直播字幕（日语 → 中文）</label>
      </div>
      <div class="hint">${subtitles.detail || "字幕显示在画面上方，增加 5 秒画面缓冲；切换开关会重启正在运行的直播推流。仅对直播转推生效。"}</div>
      <div class="hint">目标填一次即固定：之后每 60 秒验一次流，开播自动起推流、连续两次未开播自动停推流（单次抖动不误停）。
        先验流再切换，目标没在播会拒绝并保持原推流不动，勾选上项可跳过验流。关掉值守或「停止全部推流」后不再自动接管。</div>
    </section>`;
  }
}
customElements.define("live-card", LiveCard);
