// <replay-card> — 文件轮播：本地 mp4 文件或目录循环推流。
import { html } from "lit";
import * as api from "../api.js";
import { run } from "../actions.js";
import { BaseElement, loadDraft, saveDraft } from "../base.js";
import { state } from "../store.js";
import { cardHead, spinner, spinning } from "../ui.js";

class ReplayCard extends BaseElement {
  static properties = { paths: { state: true }, encode: { state: true } };

  constructor() {
    super();
    const draft = loadDraft();
    this.paths = typeof draft.paths === "string" ? draft.paths : "";
    this.encode = draft.encode === true;
  }

  #start() {
    const paths = this.paths.split("\n").map((s) => s.trim()).filter(Boolean);
    run("replay", async () => {
      await api.post("/api/mode", { mode: "replay", paths, encode: this.encode });
      return "已切换到文件轮播";
    });
  }

  render() {
    const busy = !!state.busy;
    return html`<section class="card">
      ${cardHead("replay", "文件轮播", "循环播放本地 MP4 文件或目录", "REPLAY")}
      <div class="row">
        <md-outlined-text-field class="mono" type="textarea" rows="3"
            label="绝对路径，每行一个文件或目录（目录取其中 *.mp4）" .value=${this.paths} ?disabled=${busy}
            @input=${(e) => { this.paths = e.target.value; saveDraft({ paths: this.paths }); }}></md-outlined-text-field>
      </div>
      <div class="row">
        <label class="check"><md-checkbox touch-target="wrapper" ?checked=${this.encode} ?disabled=${busy}
            @change=${(e) => { this.encode = e.target.checked; saveDraft({ encode: this.encode }); }}></md-checkbox>
          --encode 重编码（跨分段卡顿时用；默认 -c copy）</label>
        <div class="spacer"></div>
        <md-filled-button class="tonal" ?has-icon=${spinning("replay")} ?disabled=${busy}
            @click=${() => this.#start()}>${spinner("replay")}启动文件轮播</md-filled-button>
      </div>
      <div class="hint">房间关播时自动用上次分区/标题开播；无开播记录时需先去房间卡开播。</div>
    </section>`;
  }
}
customElements.define("replay-card", ReplayCard);
