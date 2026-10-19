// new-task-view.js — 新建录制任务页面。
import { html } from "lit";
import { LightElement } from "../base.js";
import "../components/app-icon.js";
import "../components/task-creation-form.js";

export class NewTaskView extends LightElement {
  render() {
    return html`
      <div class="new-task">
        <section class="panel create-panel">
          <div class="panel-title">
            <div class="title-wrap">
              <span class="section-icon"><app-icon name="add"></app-icon></span>
              <div><h2>新建录制</h2><span class="panel-kicker">选择平台并输入直播间信息</span></div>
            </div>
          </div>
          <task-creation-form></task-creation-form>
        </section>
      </div>
    `;
  }
}

customElements.define("new-task-view", NewTaskView);
