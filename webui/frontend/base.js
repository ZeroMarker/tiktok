// base.js — Lit 基础元素：订阅共享 store，store 变化即请求重渲染。
//
// 设计系统样式（styles.js）挂到每个 shadow root；跨 shadow 边界的少量规则由各
// 组件在自己的 static styles 里补（见组件注释里的「跨边界」说明）。
import { LitElement } from "lit";
import { sharedStyles } from "./styles.js";
import { subscribe } from "./stores/store.js";

export class BaseElement extends LitElement {
  static styles = [sharedStyles];

  #unsubscribe = null;

  connectedCallback() {
    super.connectedCallback();
    this.#unsubscribe = subscribe(() => this.requestUpdate());
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    if (this.#unsubscribe) this.#unsubscribe();
    this.#unsubscribe = null;
  }
}

/**
 * 参与父级布局与级联的组件用 light DOM 渲染：内容直接进入所在（shadow）树的文档流，
 * 祖先选择器（`.offline .status-pill`、`.create-panel .plat-grid`、
 * `metric-card:nth-child(n) .stat` 等）与父布局（`.jobs` 网格项、`.page-content`
 * 子元素、sticky 的 `.topbar`/`.nav`）都照常生效，无需 `:host` 变通。
 *
 * 样式来自所在地的共享样式表（styles.js），因此 light DOM 组件不声明 static styles
 * 自身样式；需要元素名的“布局透明”与位置规则写在 styles.js 里。
 * 自包含的组件（弹窗、日志、文件浏览、播放器…）仍用默认的 shadow DOM。
 */
export class LightElement extends BaseElement {
  static styles = [];

  createRenderRoot() {
    return this;
  }
}

/** 跨 shadow 边界把领域事件交给消费方（bubbles + composed）。 */
export function emit(element, type, detail) {
  element.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));
}

/** 事件最内层的真实元素（确认框点击遮罩判定用）。 */
export function clickedBackdrop(event) {
  return event.target === event.currentTarget;
}
