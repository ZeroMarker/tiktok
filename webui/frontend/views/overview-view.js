// overview-view.js — 概览：实时状态、指标、平台分布、最近任务与文件。
import { html } from "lit";
import { LightElement } from "../base.js";
import "../components/metric-card.js";
import "../components/task-list.js";
import "../components/file-browser.js";
import "../components/app-icon.js";
import { appState } from "../stores/appStore.js";
import { taskState } from "../stores/taskStore.js";
import { overviewState } from "../stores/overviewStore.js";
import { PLATFORM_ZH, LOGO_COLORS } from "../config/platforms.js";
import { fmtBytes } from "../utils.js";
import { navigate } from "../router.js";
import { openTask, askPause, askResume, askRestart, askDeleteTask } from "../actions/task-actions.js";
import { askDeleteRecording } from "../actions/recording-actions.js";

export class OverviewView extends LightElement {
  #onOpen = (event) => openTask(event.detail);
  #onPause = (event) => askPause(event.detail);
  #onResume = (event) => askResume(event.detail);
  #onRestart = (event) => askRestart(event.detail);
  #onDelete = (event) => askDeleteTask(event.detail);

  #diskPercent() { return Number(overviewState.disk_percent) || 0; }

  #diskNote() {
    if (overviewState.disk_percent == null) return "等待磁盘数据";
    return this.#diskPercent() >= 90 ? "空间紧张，建议清理文件" : "录制目录使用率";
  }

  #load1() { return overviewState.load?.[0] != null ? overviewState.load[0].toFixed(2) : "—"; }

  #memPercent() {
    return overviewState.mem_total ? ((1 - overviewState.mem_available / overviewState.mem_total) * 100).toFixed(0) + "%" : "—";
  }

  #updated() {
    return overviewState.server_time ? new Date(overviewState.server_time * 1000).toLocaleTimeString() : "—";
  }

  #platforms() { return Object.entries(overviewState.platforms || {}).sort((a, b) => b[1] - a[1]); }

  #recentJobs() {
    const query = taskState.query.trim().toLowerCase();
    return taskState.jobs
      .filter((job) => !query || (job.target + " " + job.platform + " " + job.unit).toLowerCase().includes(query))
      .slice(0, 6);
  }

  #syncText() {
    if (appState.offline) return appState.loadedOnce ? "离线模式 · 显示缓存" : "离线模式 · 等待连接";
    if (appState.degraded) return "部分数据同步失败";
    return appState.lastSynced ? "已同步 " + new Date(appState.lastSynced).toLocaleTimeString() : "等待同步";
  }

  #distWidth(count) {
    const total = this.#platforms().reduce((sum, [, n]) => sum + Number(n), 0);
    return total ? (Number(count) / total) * 100 : 0;
  }

  #showPlatform(platform) {
    taskState.platformFilter = platform;
    navigate("/tasks");
  }

  render() {
    const platforms = this.#platforms();
    const live = overviewState.live ?? overviewState.running ?? "—";
    const monitorValue = overviewState.live ?? overviewState.running;
    return html`
      <div class="overview">
        <section class="hero" aria-label="实时状态">
          <div class="hero-copy">
            <p class="eyebrow">STREAM WORKSPACE / 总览</p>
            <h2>每一场直播，都在掌握。</h2>
            <p class="hero-description">关注直播动态，管理录制任务与媒体文件。</p>
            <div class="hero-actions">
              <button class="hero-create" type="button" @click=${() => navigate("/new")}><app-icon name="add"></app-icon>新建录制任务</button>
              ${overviewState.failed
                ? html`<button class="danger" type="button" @click=${() => navigate("/tasks")}>查看 ${overviewState.failed} 个失败任务</button>`
                : html`<button class="text-button" type="button" @click=${() => navigate("/tasks")}>管理任务 →</button>`}
            </div>
          </div>
          <div class="hero-monitor">
            <div class="monitor-label"><span class="rec-dot ${monitorValue ? "" : "idle"}" aria-hidden="true"></span>${appState.offline ? "离线缓存" : appState.degraded ? "同步异常" : "直播状态"}</div>
            <div class="monitor-value"><span class="hero-num">${live}</span><span class="hero-cap">个频道直播中</span></div>
            <div class="hero-meta">
              <span>等待开播 <b>${overviewState.waiting ?? "—"}</b></span>
              <span>失败 <b class=${overviewState.failed ? "b-bad" : ""}>${overviewState.failed ?? "—"}</b></span>
            </div>
          </div>
        </section>
        <section class="stats">
          <metric-card label="直播中" icon="record" value=${live} note="个主播正在开播"></metric-card>
          <metric-card label="任务总数" icon="tasks" value=${overviewState.jobs ?? "—"} note="个托管任务"></metric-card>
          <metric-card label="可用空间" icon="storage" value=${fmtBytes(overviewState.disk_free)} note="录制目录剩余"></metric-card>
          <metric-card label="磁盘占用" icon="activity" value=${(overviewState.disk_percent ?? "—") + "%"} note=${this.#diskNote()} bar=${this.#diskPercent()}></metric-card>
        </section>
        <div class="sysinfo">
          <span>负载 <b>${this.#load1()}</b></span>
          <span>内存 <b>${this.#memPercent()}</b></span>
          <span>更新于 <b>${this.#updated()}</b></span>
          <span class="sync-status ${appState.degraded ? "warn" : ""}">${this.#syncText()}</span>
        </div>

        ${platforms.length
          ? html`
              <section class="panel" aria-label="平台任务统计">
                <div class="panel-title">
                  <div class="title-wrap"><span class="section-icon"><app-icon name="distribution"></app-icon></span><div><h2>平台分布</h2><span class="panel-kicker">托管任务占比 · 点击筛选平台</span></div></div>
                </div>
                <div class="dist">
                  ${platforms.map(([platform, count]) => html`
                    <button class="dist-row link-button" type="button" @click=${() => this.#showPlatform(platform)} title=${"查看" + (PLATFORM_ZH[platform] || platform) + "任务"}>
                      <span class="dist-name"><i class="platform-dot" style=${`background:${LOGO_COLORS[platform]}`} aria-hidden="true"></i>${PLATFORM_ZH[platform] || platform}</span>
                      <span class="dist-track"><i class="dist-fill" style=${`width:${this.#distWidth(count)}%;background:${LOGO_COLORS[platform] || ""}`}></i></span>
                      <span class="dist-num">${count} 个<span>${this.#distWidth(count).toFixed(0)}%</span></span>
                    </button>
                  `)}
                </div>
              </section>
            `
          : ""}

        <section class="panel">
          <div class="panel-title">
            <div class="title-wrap"><span class="section-icon"><app-icon name="tasks"></app-icon></span><div><h2>最近任务</h2><span class="panel-kicker">点击查看日志与详情</span></div></div>
            <div class="filter-bar">
              <input placeholder="搜索频道或平台" aria-label="搜索最近任务" .value=${taskState.query} @input=${(event) => { taskState.query = event.target.value; }}>
              <button class="secondary" type="button" @click=${() => navigate("/tasks")}>全部任务</button>
            </div>
          </div>
          <task-list
            .jobs=${this.#recentJobs()}
            ?filtered=${Boolean(taskState.query)}
            @open=${this.#onOpen}
            @pause=${this.#onPause}
            @resume=${this.#onResume}
            @restart=${this.#onRestart}
            @delete=${this.#onDelete}
          ></task-list>
        </section>

        <section class="panel">
          <div class="panel-title">
            <div class="title-wrap"><span class="section-icon"><app-icon name="library"></app-icon></span><div><h2>最近文件</h2><span class="panel-kicker">最近生成的媒体文件</span></div></div>
            <button class="secondary" type="button" @click=${() => navigate("/library")}>查看全部</button>
          </div>
          <file-browser .files=${overviewState.files || []} .total=${(overviewState.files || []).length} @delete=${(event) => askDeleteRecording(event.detail)}></file-browser>
        </section>
      </div>
    `;
  }
}

customElements.define("overview-view", OverviewView);
