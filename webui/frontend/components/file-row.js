// file-row.js — 单个录制文件行。
//
// light DOM：`.file-row` 由 file-group（shadow）里的 `.fgroup-body` 直接控制
// （含 `> file-row:last-child` 的最后一行去边框规则），所以内容必须留在
// file-group 的树里。
import { html } from "lit";
import { LightElement, emit } from "../base.js";
import { fileUrl, fmtBytes } from "../utils.js";

function fmtDate(timestamp) { return new Date(timestamp * 1000).toLocaleString(); }

export class FileRow extends LightElement {
  static properties = {
    file: { type: Object },
    active: { type: Boolean },
    pending: { type: Boolean },
  };

  render() {
    const file = this.file;
    return html`
      <div class="file-row ${this.active ? "active" : ""}">
        <div class="fname" title=${file.path}><a href=${fileUrl(file.path)} download>${file.name}</a></div>
        <div class="fmeta">${fmtBytes(file.size)} · ${fmtDate(file.modified)}</div>
        <div class="file-actions">
          <button class="mini secondary" type="button" @click=${() => emit(this, "play", file)}>${this.active ? "播放中" : "播放"}</button>
          <button class="mini danger" type="button" ?disabled=${this.pending} @click=${() => emit(this, "delete", file)}>删除</button>
        </div>
      </div>
    `;
  }
}

customElements.define("file-row", FileRow);
