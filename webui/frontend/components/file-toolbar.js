// file-toolbar.js — 文件搜索与分组展开工具条。
import { html, css } from "lit";
import { BaseElement, emit } from "../base.js";
import "../material.js";

export class FileToolbar extends BaseElement {
  static properties = {
    query: { type: String },
    localQuery: { state: true },
  };

  static styles = [...BaseElement.styles, css`:host { display: block; }`];

  #timer = null;

  constructor() {
    super();
    this.query = "";
    this.localQuery = "";
  }

  willUpdate(changed) {
    if (changed.has("query")) this.localQuery = this.query || "";
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    clearTimeout(this.#timer);
  }

  #onInput(event) {
    this.localQuery = event.target.value;
    clearTimeout(this.#timer);
    this.#timer = setTimeout(() => emit(this, "search", this.localQuery), 250);
  }

  render() {
    return html`
      <div class="log-tools">
        <md-outlined-text-field
          class="file-search"
          label="搜索文件名或目录"
          .value=${this.localQuery}
          @input=${this.#onInput}
        ></md-outlined-text-field>
        <md-text-button compact @click=${() => emit(this, "expand-all", true)}>全部展开</md-text-button>
        <md-text-button compact @click=${() => emit(this, "expand-all", false)}>全部收起</md-text-button>
      </div>
    `;
  }
}

customElements.define("file-toolbar", FileToolbar);
