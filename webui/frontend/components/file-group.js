// file-group.js — 按目录分组的录制文件（可折叠）。
//
// shadow DOM：`.fgroup` 自带样式、不依赖祖先，适合封装；内部 file-row 是 light DOM，
// 内容落在本 shadow root 里，因此「最后一行去边框」在这里表达。
import { html, css } from "lit";
import { BaseElement, emit } from "../base.js";
import "./file-row.js";

export class FileGroup extends BaseElement {
  static properties = {
    group: { type: Object },
    open: { type: Boolean },
    activePath: { type: String, attribute: "active-path" },
    pendingPath: { type: String, attribute: "pending-path" },
  };

  static styles = [
    ...BaseElement.styles,
    css`
      :host { display: block; }
      /* file-row 是 light DOM 子节点，:last-child 必须落在宿主元素上而不是 .file-row 上。 */
      .fgroup-body > file-row:last-child .file-row { border-bottom: 0; }
    `,
  ];

  render() {
    const group = this.group;
    return html`
      <div class="fgroup ${this.open ? "open" : ""}">
        <button class="fgroup-head" type="button" aria-expanded=${String(this.open)} @click=${() => emit(this, "toggle", group.dir)}>
          <span class="chevron">▶</span><span>${group.name}</span><span class="count">${group.files.length} 个文件</span>
        </button>
        <div class="fgroup-body">
          ${group.files.map((file) => html`
            <file-row
              .file=${file}
              ?active=${this.activePath === file.path}
              ?pending=${this.pendingPath === file.path}
            ></file-row>
          `)}
        </div>
      </div>
    `;
  }
}

customElements.define("file-group", FileGroup);
