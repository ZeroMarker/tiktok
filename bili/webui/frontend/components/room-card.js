// <room-card> — 直播间设置：开播（分区 + 标题）、改标题、停播、上传封面。
import { html, nothing } from "lit";
import * as api from "../api.js";
import { fail, notify, run } from "../actions.js";
import { BaseElement, loadDraft, saveDraft } from "../base.js";
import { state } from "../store.js";
import { cardHead, confirmAction, onEnter, spinner, spinning } from "../ui.js";

const MAX_COVER = 10 * 1024 * 1024;

class RoomCard extends BaseElement {
  static properties = {
    area: { state: true }, title: { state: true }, newTitle: { state: true },
    cover: { state: true }, preview: { state: true }, output: { state: true },
  };

  constructor() {
    super();
    const draft = loadDraft();
    this.area = typeof draft.area === "string" ? draft.area : "";
    this.title = typeof draft.title === "string" ? draft.title : "";
    this.newTitle = typeof draft.newTitle === "string" ? draft.newTitle : "";
    this.cover = null;
    this.preview = "";
    this.output = "";
  }

  #field(key) {
    return (e) => { this[key] = e.target.value; saveDraft({ [key]: this[key] }); };
  }

  #room(action) {
    const data = { action };
    if (action === "start") {
      data.area = parseInt(this.area, 10);
      data.title = this.title.trim();
      if (!Number.isInteger(data.area) || data.area <= 0 || !data.title) {
        return fail(new Error("请填写有效分区 ID 和标题"));
      }
    } else if (action === "update") {
      data.title = this.newTitle.trim();
    }
    run(action, async () => {
      const r = await api.post("/api/room", data);
      this.output = r.output || "OK";
      return action === "start" ? "开播成功，推流已用新码重启" : "OK";
    });
  }

  async #stop() {
    if (!(await confirmAction("停播会同时停掉全部推流（直播推流 + 文件轮播），值守也会关闭。确定停播？", "停播"))) return;
    this.#room("stop");
  }

  #pick(e) {
    const file = e.target.files[0] || null;
    if (this.preview) URL.revokeObjectURL(this.preview);
    this.cover = file;
    this.preview = file ? URL.createObjectURL(file) : "";
  }

  #upload() {
    const file = this.cover;
    if (!file) return fail(new Error("请选择封面图片"));
    if (file.size > MAX_COVER) return fail(new Error("封面文件不能超过 10 MB"));
    run("cover", async () => {
      notify("正在上传并设置封面…");
      const r = await api.uploadCover(file);
      this.output = r.output || "封面已更新";
      return "直播间封面已更新";
    }, { reload: false });
  }

  render() {
    const busy = !!state.busy;
    return html`<section class="card">
      ${cardHead("room", "直播间设置", "管理开播状态、标题、分区与封面")}
      <div class="row">
        <md-outlined-text-field class="narrow" label="子分区 ID" type="number" min="1" step="1"
            supporting-text="live.py areas 查" .value=${this.area} ?disabled=${busy}
            @input=${this.#field("area")} @keydown=${onEnter(() => this.#room("start"))}></md-outlined-text-field>
        <md-outlined-text-field label="标题（纯文本，禁 emoji，≤40 字）" maxlength="40" .value=${this.title}
            ?disabled=${busy} @input=${this.#field("title")}
            @keydown=${onEnter(() => this.#room("start"))}></md-outlined-text-field>
        <md-filled-button ?has-icon=${spinning("start")} ?disabled=${busy}
            @click=${() => this.#room("start")}>${spinner("start")}开播</md-filled-button>
      </div>
      <div class="row">
        <md-outlined-text-field label="新标题" maxlength="40" .value=${this.newTitle} ?disabled=${busy}
            @input=${this.#field("newTitle")} @keydown=${onEnter(() => this.#room("update"))}></md-outlined-text-field>
        <md-filled-button class="tonal" ?has-icon=${spinning("update")} ?disabled=${busy}
            @click=${() => this.#room("update")}>${spinner("update")}改标题</md-filled-button>
        <md-filled-button class="danger" ?has-icon=${spinning("stop")} ?disabled=${busy}
            @click=${() => this.#stop()}>${spinner("stop")}停播（同时停推流）</md-filled-button>
      </div>
      <div class="row">
        <label class="file-pick"><span class="sub-label">直播间封面（JPG / PNG / WEBP，≤10MB）</span>
          <input type="file" accept="image/jpeg,image/png,image/webp" ?disabled=${busy} @change=${(e) => this.#pick(e)}>
          <span class="hint">${this.cover ? this.cover.name : "选择图片后会在这里预览"}</span></label>
        ${this.preview ? html`<img class="cover-preview" src=${this.preview} alt="封面预览">` : nothing}
        <md-filled-button class="tonal" ?has-icon=${spinning("cover")} ?disabled=${busy}
            @click=${() => this.#upload()}>${spinner("cover")}上传并设置封面</md-filled-button>
      </div>
      ${this.output ? html`<pre>${this.output}</pre>` : nothing}
    </section>`;
  }
}
customElements.define("room-card", RoomCard);
