// global-feedback.js — 全局确认框与 toast。
import { html, css } from "lit";
import { BaseElement, clickedBackdrop } from "../base.js";
import { ui, closeConfirm } from "../ui.js";

export class GlobalFeedback extends BaseElement {
  static styles = [
    ...BaseElement.styles,
    css`
      /* 两个顶层节点（fixed 定位）不参与文档流。 */
      :host { display: block; }
      .toast[hidden] { display: none; }
    `,
  ];

  #onKeydown = (event) => {
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
      <div
        class="modal ${confirm.visible ? "" : "hidden"}"
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        aria-describedby="modal-text"
        @click=${(event) => { if (clickedBackdrop(event)) closeConfirm(); }}
      >
        <div class="modal-box">
          <h3 id="modal-title">${confirm.title}</h3>
          <p id="modal-text">${confirm.text}</p>
          <div class="modal-actions">
            <button class="secondary" type="button" @click=${closeConfirm}>取消</button>
            <button type="button" class=${confirm.danger ? "danger" : "secondary"} @click=${this.#confirm}>${confirm.okText}</button>
          </div>
        </div>
      </div>
      <div class="toast" role="status" aria-live="polite" ?hidden=${!ui.toast}>${ui.toast}</div>
    `;
  }
}

customElements.define("global-feedback", GlobalFeedback);
