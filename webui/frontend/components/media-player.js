// media-player.js — 录制文件内嵌播放器。
import { html, css } from "lit";
import { BaseElement, emit } from "../base.js";
import { fmtBytes, fileUrl } from "../utils.js";

function fmtDate(timestamp) { return new Date(timestamp * 1000).toLocaleString(); }

export class MediaPlayer extends BaseElement {
  static properties = { file: { type: Object } };

  static styles = [...BaseElement.styles, css`:host { display: block; }`];

  updated(changed) {
    if (!changed.has("file") || !this.file) return;
    this.scrollIntoView({ behavior: "smooth", block: "nearest" });
    const video = this.renderRoot.querySelector("video");
    if (video) video.play().catch(() => {});
  }

  render() {
    const file = this.file;
    if (!file) return "";
    return html`
      <div class="inline-player">
        <div class="inline-player-head">
          <span class="player-title" title=${file.path}>${file.name}</span>
          <span class="fmeta">${fmtBytes(file.size)} · ${fmtDate(file.modified)}</span>
          <a href=${fileUrl(file.path)} download class="mini secondary">下载</a>
          <button class="mini secondary" type="button" @click=${() => emit(this, "close")}>收起播放器</button>
        </div>
        <video controls autoplay playsinline src=${fileUrl(file.path)} @error=${() => emit(this, "error")}></video>
      </div>
    `;
  }
}

customElements.define("media-player", MediaPlayer);
