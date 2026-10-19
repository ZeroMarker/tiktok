// global-feedback.js — 全局确认框（md-dialog）与 toast。
import { html, css } from "lit";
import { BaseElement } from "../base.js";
import { ui, closeConfirm } from "../ui.js";
import "../material.js";

export class GlobalFeedback extends BaseElement {
  static styles = [
    ...BaseElement.styles,
    css`
      :host { display: block; }
      md-dialog { --md-dialog-container-shape: 28px; }
      .toast[hidden] { display: none; }
    `,
  ];

  #onKeydown = (event) => {
    // md-dialog 自己处理 Escape；这里只兜底“确认框未通过 dialog 打开”的极端情况。
    if (event.key === "Escape" && ui.confirm.visible) closeConfirm();
  };

  connectedCallback() {
    super.connectedCallback();
    window.addEventListener("keydown", this.#onKeydown);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    window.removeEventListener("keydown", this.#onKeydown);
  }

  #confirm = () => {
    const callback = ui.confirm.cb;
    closeConfirm();
    if (callback) callback();
  };

  render() {
    const confirm = ui.confirm;
    return html`
      <md-dialog
        .open=${Boolean(confirm.visible)}
        @closed=${() => { if (ui.confirm.visible) closeConfirm(); }}
      >
        <div slot="headline">${confirm.title}</div>
        <div slot="content" id="modal-text">${confirm.text}</div>
        <div slot="actions">
          <md-text-button @click=${closeConfirm}>取消</md-text-button>
          <md-filled-button class=${confirm.danger ? "danger" : ""} @click=${this.#confirm}>${confirm.okText}</md-filled-button>
        </div>
      </md-dialog>
      <div class="toast" role="status" aria-live="polite" ?hidden=${!ui.toast}>${ui.toast}</div>
    `;
  }
}

customElements.define("global-feedback", GlobalFeedback);
