// file-browser.js — 录制文件浏览器（搜索、分组、播放、删除、加载更多）。
import { html, css } from "lit";
import { BaseElement, emit } from "../base.js";
import "../material.js";
import "./file-toolbar.js";
import "./file-group.js";
import "./media-player.js";

export class FileBrowser extends BaseElement {
  static properties = {
    files: { type: Array },
    total: { type: Number },
    query: { type: String },
    remoteSearch: { type: Boolean, attribute: "remote-search" },
    loading: { type: Boolean },
    error: { type: String },
    pendingPath: { type: String, attribute: "pending-path" },
    playing: { state: true },
    collapsed: { state: true },
    localQuery: { state: true },
  };

  static styles = [...BaseElement.styles, css`:host { display: block; }`];

  constructor() {
    super();
    this.files = [];
    this.playing = null;
    this.collapsed = null;
    this.localQuery = "";
  }

  #displayFiles() {
    if (this.remoteSearch || !this.localQuery.trim()) return this.files;
    const query = this.localQuery.trim().toLowerCase();
    return this.files.filter((file) => (file.name + " " + file.dir).toLowerCase().includes(query));
  }

  #groups() {
    const map = new Map();
    for (const file of this.#displayFiles()) {
      const dir = file.dir || "";
      if (!map.has(dir)) map.set(dir, { dir, name: dir || "根目录", files: [] });
      map.get(dir).files.push(file);
    }
    return [...map.values()];
  }

  #activeQuery() { return this.remoteSearch ? (this.query || "") : this.localQuery; }

  #hasMore() { return this.remoteSearch && this.files.length < (this.total || 0); }

  #onSearch(value) {
    if (this.remoteSearch) emit(this, "search", value);
    else this.localQuery = value;
  }

  #isOpen(dir, groups) {
    return this.collapsed === null ? groups[0]?.dir === dir : !this.collapsed.has(dir);
  }

  #toggle(dir, groups) {
    if (this.collapsed === null) this.collapsed = new Set(groups.map((group) => group.dir));
    if (this.collapsed.has(dir)) this.collapsed.delete(dir); else this.collapsed.add(dir);
    this.collapsed = new Set(this.collapsed);
  }

  #expandAll(open) {
    this.collapsed = new Set(open ? [] : this.#displayFiles().map((file) => file.dir));
  }

  render() {
    const groups = this.#groups();
    const activeQuery = this.#activeQuery();
    return html`
      <div class="files-panel">
        <file-toolbar
          .query=${this.remoteSearch ? this.query : this.localQuery}
          @search=${(event) => this.#onSearch(event.detail)}
          @expand-all=${(event) => this.#expandAll(event.detail)}
        ></file-toolbar>
        <media-player .file=${this.playing} @close=${() => { this.playing = null; }}></media-player>
        ${this.loading && !this.files.length
          ? html`<div class="loading-state" role="status">正在加载文件…</div>`
          : this.error && !this.files.length
            ? html`<div class="error-state" role="alert"><span>${this.error}</span><md-text-button compact @click=${() => emit(this, "retry")}>重试</md-text-button></div>`
            : !groups.length
              ? html`<div class="empty"><strong>${activeQuery ? "没有匹配的文件" : "暂无录制文件"}</strong><span>${activeQuery ? "请尝试其他关键词" : "录制完成后，文件会显示在这里"}</span></div>`
              : html`
                  <div class="files">
                    ${groups.map((group) => html`
                      <file-group
                        .group=${group}
                        ?open=${this.#isOpen(group.dir, groups)}
                        active-path=${this.playing ? this.playing.path : ""}
                        pending-path=${this.pendingPath || ""}
                        @toggle=${(event) => this.#toggle(event.detail, groups)}
                        @play=${(event) => { this.playing = event.detail; }}
                        @delete=${(event) => emit(this, "delete", event.detail)}
                      ></file-group>
                    `)}
                    ${this.error ? html`<div class="inline-error" role="alert">${this.error} <md-text-button compact @click=${() => emit(this, "retry")}>重试</md-text-button></div>` : ""}
                    ${this.#hasMore()
                      ? html`<md-outlined-button class="load-more" ?disabled=${this.loading} @click=${() => emit(this, "load-more")}>${this.loading ? "加载中…" : `加载更多（${this.files.length}/${this.total}）`}</md-outlined-button>`
                      : ""}
                  </div>
                `}
      </div>
    `;
  }
}

customElements.define("file-browser", FileBrowser);
