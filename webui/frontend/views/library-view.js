// library-view.js — 录制文件库（平台过滤 + 服务端搜索）。
import { html } from "lit";
import { LightElement } from "../base.js";
import "../components/app-icon.js";
import "../components/file-browser.js";
import { recordingState, refreshRecordings, loadMoreRecordings } from "../stores/recordingStore.js";
import { PLATFORM_ZH } from "../utils.js";
import { PLATFORM_KEYS } from "../config/platforms.js";
import { askDeleteRecording } from "../actions/recording-actions.js";

export class LibraryView extends LightElement {
  static properties = {
    platformFilter: { state: true },
    fileQuery: { state: true },
  };

  constructor() {
    super();
    this.platformFilter = "all";
    this.fileQuery = "";
  }

  // 平台过滤在客户端按顶层目录（recordings/<platform>/…）判定：
  // 后端 q 是整体子串匹配，把平台名拼进 q 会导致组合条件永远为空。
  #visibleFiles() {
    if (this.platformFilter === "all") return recordingState.files;
    return recordingState.files.filter((file) => (file.dir || "").split("/")[0] === this.platformFilter);
  }

  #visibleTotal() {
    return this.platformFilter === "all" ? recordingState.total : this.#visibleFiles().length;
  }

  #countText() { return this.#visibleFiles().length ? `${this.#visibleTotal()} 个` : "无文件"; }

  #loadFiles = async () => {
    const query = this.fileQuery.trim();
    recordingState.query = query;
    // 平台过滤时一次取足（后端上限 500），保证过滤视图完整，同时让后台同步/删除后刷新沿用同一条数。
    recordingState.limit = this.platformFilter === "all" ? 80 : 500;
    try {
      await refreshRecordings({ query, offset: 0 });
    } catch {
      // 错误已写入录制文件状态，由 FileBrowser 展示重试入口。
    }
  };

  #onSearch = (event) => {
    this.fileQuery = event.detail;
    this.#loadFiles();
  };

  #loadMore = async () => {
    if (this.platformFilter !== "all") return;
    try {
      await loadMoreRecordings();
    } catch {
      // 错误已写入全局状态。
    }
  };

  #onDelete = (event) => askDeleteRecording(event.detail);

  updated(changed) {
    if (changed.has("platformFilter")) this.#loadFiles();
  }

  render() {
    const files = this.#visibleFiles();
    return html`
      <div class="library">
        <section class="panel">
          <div class="panel-title">
            <div class="title-wrap">
              <span class="section-icon"><app-icon name="library"></app-icon></span>
              <div>
                <h2>录制文件<span class="count">${this.#countText()}</span></h2>
                <span class="panel-kicker">按平台/目录浏览，播放、下载或清理</span>
              </div>
            </div>
            <div class="seg" role="tablist" aria-label="平台过滤">
              <button class="seg-btn ${this.platformFilter === "all" ? "on" : ""}" type="button" @click=${() => { this.platformFilter = "all"; }}>全部</button>
              ${PLATFORM_KEYS.map((platform) => html`
                <button class="seg-btn ${this.platformFilter === platform ? "on" : ""}" type="button" @click=${() => { this.platformFilter = platform; }}>${PLATFORM_ZH[platform] || platform}</button>
              `)}
            </div>
            <button class="mini secondary" type="button" ?disabled=${recordingState.busy} @click=${this.#loadFiles}>${recordingState.busy ? "加载中…" : "刷新"}</button>
          </div>
          <file-browser
            .files=${files}
            .total=${this.#visibleTotal()}
            .query=${this.fileQuery}
            remote-search
            ?loading=${recordingState.busy}
            .error=${recordingState.error}
            .pendingPath=${recordingState.pendingPath}
            @search=${this.#onSearch}
            @load-more=${this.#loadMore}
            @retry=${this.#loadFiles}
            @delete=${this.#onDelete}
          ></file-browser>
        </section>
      </div>
    `;
  }
}

customElements.define("library-view", LibraryView);
