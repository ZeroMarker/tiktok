// base.js — Lit 基础元素：订阅共享 store，store 变化即请求重渲染。
//
// 全部组件用 light DOM：样式是挂在 document 上的一张全局表（styles.js），卡片网格、
// 粘性状态卡这类父级布局规则直接作用到子组件内容；Material 组件自带 shadow DOM，
// 外观只经 --md-* token 定制（自定义属性可穿透 shadow 边界）。
import { LitElement } from "lit";
import { subscribe } from "./store.js";

export class BaseElement extends LitElement {
  #unsubscribe = null;

  createRenderRoot() {
    return this;
  }

  connectedCallback() {
    super.connectedCallback();
    this.#unsubscribe = subscribe(() => this.requestUpdate());
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this.#unsubscribe?.();
    this.#unsubscribe = null;
  }
}

/** 本地草稿：表单输入存 localStorage，刷新页面不丢（键沿用旧版 bili-form-v1）。 */
const DRAFT_KEY = "bili-form-v1";

export function loadDraft() {
  try {
    return JSON.parse(localStorage.getItem(DRAFT_KEY) || "{}") || {};
  } catch {
    return {};
  }
}

export function saveDraft(patch) {
  try {
    localStorage.setItem(DRAFT_KEY, JSON.stringify({ ...loadDraft(), ...patch }));
  } catch {
    /* 浏览器禁用存储时仍可使用 */
  }
}
