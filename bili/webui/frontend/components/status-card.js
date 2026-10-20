// <status-card> — 运行概览：当前模式、两个推流单元、固定目标开播状态（值守快照）、房间状态。
import { html } from "lit";
import { BaseElement } from "../base.js";
import { state } from "../store.js";
import { cardHead, unitLine, unitPill } from "../ui.js";

const MODE_NAMES = { live: "直播推流", replay: "文件轮播", idle: "空闲", conflict: "冲突！双推流" };

function targetView(t) {
  if (!t.target) return { pill: ["未设置目标", "bad"], name: "未设置目标主播" };
  const pill = t.live === true ? ["开播中", "live"] : t.live === false ? ["未开播", ""] : ["待检测", ""];
  return { pill, name: `@${t.target} · ${t.armed ? "值守中" : "值守已关"}` };
}

class StatusCard extends BaseElement {
  render() {
    const s = state.status;
    const head = cardHead("status", "运行概览", "推流服务与直播间的实时状态");
    if (!s) {
      return html`<section class="card">${head}
        <div class="mode-hero"><span class="mode-dot"></span>
          <div><div class="mode-name">…</div><div class="hint">${state.online ? "正在连接…" : "连接失败，稍后自动重试"}</div></div>
        </div></section>`;
    }
    const t = s.target || {};
    const tv = targetView(t);
    const dot = s.mode === "idle" ? "" : s.mode === "conflict" ? "warn" : "on";
    const [livePill, liveCls] = unitPill(s.live);
    const [replayPill, replayCls] = unitPill(s.replay);
    const when = t.checked
      ? `上次检测 ${t.checked}（${Math.round(t.age)} 秒前）${t.next != null ? ` · 下次 ${t.next} 秒后` : ""}`
      : "等待首次检测（每 60 秒一轮）";
    return html`<section class="card">
      ${head}
      <div class="mode-hero">
        <span class="mode-dot ${dot}"></span>
        <div>
          <div class="mode-name">${MODE_NAMES[s.mode] || s.mode}</div>
          <div class="hint" aria-live="polite">${state.online
            ? `更新于 ${state.refreshedAt} · 每 10 秒刷新`
            : "刷新失败 · 当前显示为上次结果"}</div>
        </div>
      </div>
      <div class="row">
        <div class="svc"><div class="t">直播推流 <span class="pill ${liveCls}">${livePill}</span></div>
          <div class="s">${unitLine(s.live)}</div>
          <div class="s" ?hidden=${!s.live.target}>固定目标 @${s.live.target}</div>
          <div class="s">直播字幕：${s.subtitles?.enabled ? "已开启 · 顶部显示 · 缓冲 5 秒" : "已关闭"}</div></div>
        <div class="svc"><div class="t">文件轮播 <span class="pill ${replayCls}">${replayPill}</span></div>
          <div class="s">${unitLine(s.replay)}</div>
          <div class="s" ?hidden=${!s.replay.args}>${s.replay.args}</div></div>
      </div>
      <div class="sub-head"><span class="sub-label">固定目标开播状态</span>
        <span class="pill ${tv.pill[1]}">${tv.pill[0]}</span></div>
      <div class="row">
        <div class="svc"><div class="t">${tv.name}</div>
          <div class="s">${when}</div>
          <div class="s">${t.detail || ""}${t.source === "push" ? " · 推流中免探测" : ""}</div></div>
      </div>
      <div class="sub-head"><span class="sub-label">房间状态</span>
        <span class="pill ${s.room.ok ? "live" : "bad"}">${s.room.ok ? "已登录" : "异常"}</span></div>
      <pre>${s.room.text || "(房间状态未知)"}</pre>
    </section>`;
  }
}
customElements.define("status-card", StatusCard);
