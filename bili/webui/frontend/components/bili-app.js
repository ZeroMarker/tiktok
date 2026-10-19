// <bili-app> — 外壳：顶栏、操作进度条、提示横幅、五张卡片、toast、确认对话框。
import { html } from "lit";
import { refresh, dismissToast } from "../actions.js";
import { BaseElement } from "../base.js";
import { state } from "../store.js";
import { icon } from "../ui.js";

class BiliApp extends BaseElement {
  #confirmText = "";
  #confirmLabel = "确定";
  #resolve = null;

  confirm(message, confirmLabel = "确定") {
    this.#confirmText = message;
    this.#confirmLabel = confirmLabel;
    this.requestUpdate();
    return new Promise((resolve) => {
      this.#resolve = resolve;
      this.updateComplete.then(() => this.querySelector("#confirm").show());
    });
  }

  #closed(e) {
    this.#resolve?.(e.target.returnValue === "ok");
    this.#resolve = null;
  }

  render() {
    const { online, busy, notice, toast } = state;
    return html`
      <header class="topbar">
        <div class="logo">${icon("logo", 22)}</div>
        <div><h1>Bili 推流管理</h1><div class="sub">TikTok 转播 · 文件轮播 · B 站房间</div></div>
        <div class="spacer"></div>
        <div class="online ${online ? "" : "offline"}">${online ? "控制台在线" : "连接异常"}</div>
        <md-filled-button class="tonal" has-icon ?disabled=${!!busy} title="刷新状态"
            @click=${() => refresh()}><span slot="icon">${icon("refresh")}</span>刷新</md-filled-button>
      </header>
      <main class="wrap">
        <md-linear-progress class="busy-bar ${busy ? "" : "idle"}" ?indeterminate=${!!busy}
            aria-hidden="true"></md-linear-progress>
        <div class="notice ${notice.error ? "error" : ""}" role="status" aria-live="polite">${notice.text}</div>
        <status-card></status-card>
        <live-card></live-card>
        <replay-card></replay-card>
        <room-card></room-card>
        <logs-card></logs-card>
        <div class="foot">BiliPushWebUI · 仅监听回环地址</div>
      </main>
      <button class="toast ${toast ? "show" : ""} ${toast?.error ? "err" : ""}" aria-live="polite"
          @click=${dismissToast}>${toast?.text ?? ""}</button>
      <md-dialog id="confirm" @closed=${this.#closed}>
        <div slot="headline">请确认</div>
        <form slot="content" id="confirm-form" method="dialog">${this.#confirmText}</form>
        <div slot="actions">
          <md-text-button form="confirm-form" value="cancel">取消</md-text-button>
          <md-filled-button class="danger" form="confirm-form" value="ok">${this.#confirmLabel}</md-filled-button>
        </div>
      </md-dialog>`;
  }
}
customElements.define("bili-app", BiliApp);
