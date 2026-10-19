// styles.js — 设计系统样式表。
//
// 控件（按钮/输入/下拉/复选/对话框/标签）由 @material/web 提供，外观通过 MD3 token
// 覆盖；本文件只保留：
//   1) MD3 token 桥接（把原调色板映射成 --md-sys-color-*，深色 + 薄荷绿）
//   2) 布局与自有组件（外壳、面板、任务行、文件树、日志台、Toast）
//   3) light DOM 组件的“布局透明”规则
// 全局挂一次（document）让 :root/html/body 生效；同时作为每个 shadow root 的样式表。

import { css, unsafeCSS } from "lit";

export const cssText = /* css */ `
:root,:host{
  /* ── 原调色板（自有组件继续用） ── */
  --pri:#9be8c5;--on-pri:#00382a;--pri-cont:#07533f;--on-pri-cont:#b7f4d5;
  --sec:#b9ccc3;--on-sec:#24332e;--sec-cont:#354b43;--on-sec-cont:#d5e9df;
  --ter:#a9cbed;--on-ter-cont:#d1e7ff;
  --err:#ffb4ab;--err-cont:#93000a;--on-err-cont:#ffd9d4;
  --surf:#0b1210;--surf-low:#111a17;--surf-cont:#17221f;--surf-high:#222e2a;--surf-highest:#2d3935;
  --outl:#899791;--outl-var:#3e4944;
  --s-sm:10px;--s-md:16px;--s-lg:24px;--s-xl:32px;--s-full:999px;
  --ease:cubic-bezier(.2,0,0,1);--dur-s:150ms;
  --bg:var(--surf);--bg-soft:var(--surf-low);--panel:var(--surf-cont);--panel2:var(--surf-high);
  --line:var(--outl-var);--line-strong:var(--outl);--text:var(--on-pri-cont);--muted:var(--sec);
  --brand:var(--pri);--brand-strong:var(--pri);--blue:var(--ter);--warn:#f5bd62;--red:var(--err);--live:#ff9090;
  --shadow:0 10px 34px rgba(0,0,0,.2);--shadow-hover:0 18px 44px rgba(0,0,0,.28);--radius:var(--s-lg);
  color-scheme:dark;

  /* ── MD3 token 桥接（深色 + 薄荷绿）── */
  --md-sys-color-primary:var(--pri);            --md-sys-color-on-primary:var(--on-pri);
  --md-sys-color-primary-container:var(--pri-cont); --md-sys-color-on-primary-container:var(--on-pri-cont);
  --md-sys-color-secondary:var(--sec);          --md-sys-color-on-secondary:var(--on-sec);
  --md-sys-color-secondary-container:var(--sec-cont); --md-sys-color-on-secondary-container:var(--on-sec-cont);
  --md-sys-color-tertiary:var(--ter);           --md-sys-color-on-tertiary:#0a2438;
  --md-sys-color-tertiary-container:#173a56;    --md-sys-color-on-tertiary-container:var(--on-ter-cont);
  --md-sys-color-error:var(--err);              --md-sys-color-on-error:#690005;
  --md-sys-color-error-container:var(--err-cont); --md-sys-color-on-error-container:var(--on-err-cont);
  --md-sys-color-surface:var(--surf);           --md-sys-color-on-surface:var(--on-pri-cont);
  --md-sys-color-surface-variant:var(--surf-high); --md-sys-color-on-surface-variant:var(--sec);
  --md-sys-color-surface-container-lowest:#070d0b;
  --md-sys-color-surface-container-low:var(--surf-low);
  --md-sys-color-surface-container:var(--surf-cont);
  --md-sys-color-surface-container-high:var(--surf-high);
  --md-sys-color-surface-container-highest:var(--surf-highest);
  --md-sys-color-outline:var(--outl);           --md-sys-color-outline-variant:var(--outl-var);
  --md-sys-color-shadow:#000;                   --md-sys-color-scrim:#000;
  --md-sys-color-inverse-surface:var(--on-pri-cont); --md-sys-color-inverse-on-surface:var(--surf-cont);
  --md-sys-color-inverse-primary:var(--pri-cont);
  --md-sys-color-background:var(--surf);        --md-sys-color-on-background:var(--on-pri-cont);
  --md-sys-color-surface-tint:var(--pri);
  --md-sys-typescale-body-large-font:"Google Sans Text","Noto Sans",Inter,ui-sans-serif,system-ui,"PingFang SC","Microsoft YaHei",sans-serif;
  --md-sys-typescale-label-large-font:var(--md-sys-typescale-body-large-font);
  --md-sys-typescale-title-large-font:var(--md-sys-typescale-body-large-font);
  --md-dialog-container-color:var(--surf-cont);
  --md-dialog-headline-color:var(--on-pri-cont);
  --md-dialog-supporting-text-color:var(--sec);
  --md-menu-container-color:var(--surf-high);
  --md-menu-container-shape:14px;
  --md-focus-ring-color:var(--ter);
}
*,*::before,*::after{box-sizing:border-box}
html{background:var(--surf)}
body{min-height:100vh;margin:0;background:radial-gradient(1000px 560px at 82% -10%,rgba(155,232,197,.105),transparent 68%),radial-gradient(700px 460px at -8% 45%,rgba(169,203,237,.045),transparent 70%),var(--surf);color:var(--on-pri-cont);font:14px/1.5 "Google Sans Text","Noto Sans",Inter,ui-sans-serif,system-ui,"PingFang SC","Microsoft YaHei",sans-serif;letter-spacing:0}
::selection{background:rgba(155,232,197,.28)}
*{scrollbar-width:thin;scrollbar-color:var(--outl-var) transparent}

/* ── 外壳与布局 ── */
.shell{position:relative;max-width:1520px;margin:auto;padding:28px 32px calc(72px + env(safe-area-inset-bottom))}
.shell:before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;background-image:linear-gradient(rgba(255,255,255,.012) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.012) 1px,transparent 1px);background-size:48px 48px;mask-image:linear-gradient(to bottom,black,transparent 70%)}
h1{font-size:24px;line-height:1.2;letter-spacing:-.03em;margin:0}
h2{margin:0}
h3{margin:0}
.eyebrow{margin:0 0 3px;color:var(--pri);font-size:11px;font-weight:700;letter-spacing:.13em;text-transform:uppercase}
.sub{margin:6px 0 0;color:var(--sec);font-size:13px}
.workspace{display:grid;grid-template-columns:184px minmax(0,1fr);gap:28px;align-items:start}
.page-content{min-width:0;outline:none}
.skip-link{position:fixed;top:12px;left:24px;z-index:80;padding:12px 18px;border-radius:12px;background:var(--pri);color:var(--on-pri);transform:translateY(-160%)}
.skip-link:focus{transform:none}
a{color:var(--ter)}
a:hover{color:var(--pri)}

/* 顶栏 */
.topbar{position:sticky;top:12px;z-index:40;display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:28px;padding:10px 16px;border:1px solid rgba(137,151,145,.34);border-radius:22px;background:rgba(13,22,19,.82);backdrop-filter:blur(22px) saturate(125%);-webkit-backdrop-filter:blur(22px) saturate(125%);box-shadow:0 8px 24px rgba(0,0,0,.15),inset 0 1px 0 rgba(255,255,255,.045)}
.brand{display:flex;align-items:center;gap:14px;min-width:0}
.brand-mark{position:relative;flex:none;width:42px;height:42px;border:1px solid rgba(155,232,197,.42);border-radius:15px;background:linear-gradient(145deg,#12664f,#082d25 72%);box-shadow:inset 0 1px 0 rgba(255,255,255,.14),0 8px 22px rgba(0,0,0,.22)}
.brand-mark:before,.brand-mark:after{content:"";position:absolute;border-radius:50%}
.brand-mark:before{width:12px;height:12px;left:10px;top:11px;background:var(--pri);box-shadow:12px 10px 0 -3px rgba(155,232,197,.5)}
.brand-mark:after{width:20px;height:2px;left:11px;bottom:10px;background:rgba(183,244,213,.75);border-radius:3px}
.head-right{display:flex;flex-direction:row;align-items:center;gap:8px;flex-wrap:wrap;justify-content:flex-end}
.status-pill{height:34px;display:inline-flex;align-items:center;gap:9px;padding:0 14px;border:1px solid var(--outl-var);border-radius:var(--s-full);background:var(--surf-low);font-size:12px}
.online{display:flex;align-items:center;gap:8px;color:var(--on-pri-cont);font-weight:650}
.dot{width:8px;height:8px;border-radius:50%;background:var(--pri);box-shadow:0 0 12px var(--pri);animation:pulse 2.4s var(--ease) infinite}
.clock-pill{height:34px;display:inline-flex;align-items:center;padding:0 14px;border:1px solid var(--outl-var);border-radius:var(--s-full);background:var(--surf-low);color:var(--sec);font-size:12px;font-variant-numeric:tabular-nums}
.offline .status-pill{border-color:rgba(255,180,171,.4)}
.degraded .status-pill{border-color:rgba(245,189,98,.4)}
.degraded .dot{background:var(--warn);box-shadow:0 0 12px var(--warn)}
.offline .dot{background:var(--err);box-shadow:0 0 12px var(--err)}
.spinning{animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes pulse{50%{opacity:.55}}

/* 侧栏导航（md-list） */
.nav{position:sticky;top:126px;margin:0;padding:0;background:transparent}
.nav-label{margin:4px 12px 10px;color:var(--sec);font-size:11px;letter-spacing:.12em}
.nav md-list-item{--md-list-item-label-text-color:var(--sec);--md-list-item-label-text-weight:700;border-radius:12px;margin-bottom:2px;--md-list-item-one-line-container-height:46px}
.nav md-list-item[active]{--md-list-item-label-text-color:var(--on-pri-cont);--md-list-item-container-color:var(--pri-cont);box-shadow:inset 0 0 0 1px rgba(155,232,197,.2)}
.nav-note{display:flex;align-items:flex-start;gap:10px;margin:28px 12px 0;padding-top:18px;border-top:1px solid var(--outl-var);color:var(--pri);font-size:12px}
.nav-note small{display:block;margin-top:6px;color:var(--sec);font-size:11px;line-height:1.7}
.app-icon{display:block;width:18px;height:18px;fill:currentColor;flex:none}

/* 状态行 / 横幅 */
.statusline{min-height:34px;margin:0 0 10px;padding:7px 12px;border:1px solid transparent;border-radius:var(--s-sm);color:var(--sec);font-size:12px}
.statusline.warn{border-color:rgba(255,180,171,.3);background:rgba(147,0,10,.16);color:var(--err)}
.status-retry{min-height:26px;padding:2px 9px;border:1px solid currentColor;border-radius:7px;background:transparent;color:inherit;font-size:11px;cursor:pointer}
.error-banner{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:10px 0;padding:10px 12px;border:1px solid rgba(255,180,171,.3);border-radius:var(--s-md);background:rgba(147,0,10,.16);color:var(--err);font-size:12px}
.error-banner .status-retry{margin-left:auto}
.sync-status{color:var(--sec);font-size:11px;margin-left:auto}
.b-warn,.warn{color:var(--warn)}
.b-bad{color:var(--err)}
.b-good{color:var(--pri)}
.b-live{color:var(--live)}
.b-info{color:var(--ter)}
.b-muted{color:var(--sec)}

/* Hero */
.hero{position:relative;display:flex;justify-content:space-between;align-items:center;gap:28px;flex-wrap:wrap;margin-top:0;padding:32px;border:1px solid rgba(155,232,197,.22);border-radius:24px;background:radial-gradient(540px 250px at 4% 0%,rgba(155,232,197,.15),transparent 70%),linear-gradient(135deg,rgba(23,34,31,.98),rgba(17,26,23,.96));box-shadow:var(--shadow),inset 0 1px 0 rgba(255,255,255,.045);overflow:hidden}
.hero:after{content:"";position:absolute;right:-36px;top:-72px;width:210px;height:210px;border:1px solid rgba(155,232,197,.08);border-radius:50%;box-shadow:0 0 0 34px rgba(155,232,197,.025),0 0 0 68px rgba(155,232,197,.015);pointer-events:none}
.hero>*{position:relative;z-index:1}
.hero-copy{flex:1;min-width:0}
.hero-copy h2{margin:12px 0 10px;font-size:clamp(23px,2.3vw,32px);line-height:1.4;letter-spacing:-.04em;color:var(--on-pri-cont)}
.hero-description{margin:0;color:var(--sec);font-size:13px}
.hero-actions{margin:24px 0 0;display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.hero-monitor{flex:0 0 240px;padding:20px 24px;border:1px solid rgba(155,232,197,.2);border-radius:18px;background:rgba(11,18,16,.45)}
.monitor-label{display:flex;align-items:center;gap:8px;color:var(--sec);font-size:12px}
.rec-dot{width:7px;height:7px;flex:none;border-radius:50%;background:var(--err);box-shadow:0 0 16px var(--err);animation:pulse 1.6s ease-in-out infinite}
.rec-dot.idle{background:var(--outl);box-shadow:none;animation:none}
.monitor-value{display:flex;align-items:baseline;gap:12px;margin:18px 0}
.hero-num{font-size:52px;line-height:1;font-weight:800;letter-spacing:-.04em;font-variant-numeric:tabular-nums}
@supports((background-clip:text) or (-webkit-background-clip:text)){
  .hero-num{background:linear-gradient(180deg,#eafff3 20%,var(--pri));-webkit-background-clip:text;background-clip:text;color:transparent}
}
.hero-cap{font-size:12px;letter-spacing:0;font-weight:500;color:var(--sec)}
.hero-meta{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;padding-top:12px;border-top:1px solid var(--outl-var);color:var(--sec);font-size:12px}
.hero-meta b{color:var(--on-pri-cont);font-variant-numeric:tabular-nums}

/* 指标卡 */
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-top:18px}
.stat{position:relative;min-height:148px;padding:20px;border:1px solid rgba(137,151,145,.28);border-radius:18px;background:linear-gradient(145deg,rgba(24,36,32,.98),rgba(20,30,27,.98));box-shadow:0 4px 18px rgba(0,0,0,.1),inset 0 1px 0 rgba(255,255,255,.035);overflow:hidden;transition:transform var(--dur-s) var(--ease),border-color var(--dur-s) var(--ease)}
.stat:hover{transform:translateY(-2px);border-color:rgba(155,232,197,.38)}
.stat:after{content:"";position:absolute;width:84px;height:84px;right:-34px;bottom:-38px;border-radius:50%;background:var(--pri);opacity:.035}
.stat-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:18px}
.stat-label{color:var(--sec);font-size:12px;font-weight:700}
.stat-icon{width:32px;height:32px;display:grid;place-items:center;border:1px solid var(--outl-var);border-radius:var(--s-sm);background:var(--surf-high);color:var(--pri)}
.stat-icon .app-icon{width:17px;height:17px}
.stat b{font-size:30px;line-height:1;letter-spacing:-.03em;font-variant-numeric:tabular-nums;color:var(--on-pri-cont)}
.stat-note{display:block;margin-top:8px;color:var(--sec);font-size:12px}
metric-card:nth-child(1) .stat-icon,metric-card:nth-child(1) .stat b{color:var(--live)}
metric-card:nth-child(2) .stat-icon,metric-card:nth-child(2) .stat b{color:var(--ter)}
metric-card:nth-child(3) .stat-icon,metric-card:nth-child(3) .stat b{color:var(--warn)}
metric-card:nth-child(4) .stat-icon,metric-card:nth-child(4) .stat b{color:#7dd8c6}
.stat md-linear-progress{--md-linear-progress-track-height:4px;--md-linear-progress-active-indicator-height:4px;margin-top:12px;width:100%}
.sysinfo{display:flex;align-items:center;flex-wrap:wrap;gap:8px 0;margin:12px 0 0;padding:8px 4px;color:var(--sec);font-size:12px}
.sysinfo span{display:inline-flex;align-items:center;gap:6px}
.sysinfo span+span:before{content:"";width:3px;height:3px;margin:0 12px;border-radius:50%;background:var(--outl-var)}
.sysinfo b{color:var(--on-pri-cont);font-weight:600}

/* 面板 */
.panel{padding:24px;margin-top:20px;border:1px solid rgba(137,151,145,.28);border-radius:20px;background:linear-gradient(145deg,rgba(24,36,32,.98),rgba(20,30,27,.98));box-shadow:0 4px 18px rgba(0,0,0,.1),inset 0 1px 0 rgba(255,255,255,.035)}
.panel-title{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:18px}
.title-wrap{display:flex;align-items:center;gap:12px;min-width:0}
.section-icon{width:38px;height:38px;flex:none;display:grid;place-items:center;border:1px solid var(--outl-var);border-radius:12px;background:var(--surf-high);color:var(--pri)}
.section-icon .app-icon{width:18px;height:18px}
.panel-title h2{font-size:17px;letter-spacing:-.01em;color:var(--on-pri-cont);overflow-wrap:anywhere}
.panel-kicker{display:block;color:var(--sec);font-size:12px;margin-top:4px;font-weight:400}
.count{margin-left:6px;padding:1px 8px;border-radius:var(--s-full);background:var(--surf-high);color:var(--sec);font-size:10px;font-weight:800;vertical-align:middle}
.count.warn{background:rgba(245,189,98,.18);color:var(--warn)}

/* 平台分布 */
.dist{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:6px}
.dist-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:14px 16px;border:1px solid var(--outl-var);border-radius:14px;background:var(--surf-low);min-height:86px;text-align:left;font:inherit;color:inherit;cursor:pointer;transition:border-color var(--dur-s) var(--ease),background var(--dur-s) var(--ease)}
.dist-row:hover{border-color:var(--pri);background:var(--surf-cont)}
.dist-name{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--on-pri-cont);font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.platform-dot{width:7px;height:7px;border-radius:50%;flex:none}
.dist-track{grid-column:1/-1;grid-row:2;height:4px;border-radius:var(--s-full);background:var(--surf-highest);overflow:hidden}
.dist-fill{display:block;height:100%;border-radius:inherit}
.dist-num{text-align:right;color:var(--on-pri-cont);font-variant-numeric:tabular-nums;font-size:13px}
.dist-num span{margin-left:8px;color:var(--sec);font-size:11px}

/* 任务 */
.jobs{display:grid;gap:10px}
.task-group{margin-bottom:18px}
.task-group:last-child{margin-bottom:0}
.task-group-title{display:flex;align-items:center;gap:8px;margin:0 2px 8px;color:var(--sec);font-size:11px;font-weight:800;letter-spacing:.1em;text-transform:uppercase}
.task-group-title .gdot{width:7px;height:7px;border-radius:50%;background:currentColor}
.task-group-title .count{margin-left:auto}
.job{position:relative;display:grid;grid-template-columns:46px minmax(0,1fr) auto;gap:14px;padding:14px 16px;border:1px solid var(--outl-var);border-radius:var(--s-md);background:var(--surf-low);overflow:hidden;transition:border-color var(--dur-s) var(--ease),background var(--dur-s) var(--ease)}
.job:before{content:"";position:absolute;left:0;top:14px;bottom:14px;width:2px;background:var(--state-color,var(--outl-var));border-radius:0 3px 3px 0}
.job[data-state="active"]{--state-color:var(--pri)}
.job[data-state="failed"]{--state-color:var(--err)}
.job[data-state="paused"],.job[data-live="paused"]{--state-color:var(--ter)}
.job[data-live="live"]{--state-color:var(--live)}
.job[data-live="waiting"]{--state-color:var(--warn)}
.job:hover{border-color:var(--outl);background:var(--surf-cont)}
.job.sel{border-color:var(--pri);box-shadow:inset 0 0 0 1px rgba(155,232,197,.25)}
.logo{width:46px;height:46px;display:grid;place-items:center;border:1px solid var(--pc,var(--outl-var));border-radius:var(--s-md);background:color-mix(in srgb,var(--pc,#9be8c5) 14%,var(--surf-high));font-size:12px;font-weight:800}
.job-main{min-width:0}
.job-heading{display:flex;align-items:center;gap:9px;min-width:0}
.job-title{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:0;border:0;background:transparent;color:var(--on-pri-cont);font:inherit;font-weight:650;text-align:left;cursor:pointer}
.job-title:hover{color:var(--pri)}
.platform-tag{flex:none;padding:2px 7px;border:1px solid var(--pc,var(--outl-var));border-radius:var(--s-full);background:color-mix(in srgb,var(--pc,#9be8c5) 10%,var(--surf-high));color:var(--pc,var(--sec));font-size:9px;font-weight:700;letter-spacing:.05em;text-transform:uppercase}
.job-facts{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:6px;color:var(--sec);font-size:12px}
.job-facts span+span:before{content:"·";margin-right:8px;color:var(--outl-var)}
.status{display:inline-flex;align-items:center;gap:6px;color:var(--sec)}
.status:before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor;box-shadow:0 0 8px currentColor}
.status.b-live:before{animation:pulse 1.6s ease-in-out infinite}
.actions{display:flex;gap:6px;flex-wrap:wrap;align-items:center}

/* 详情 */
.split{display:grid;grid-template-columns:1.3fr .7fr;gap:20px}
.split>.panel{min-width:0}
.kv{display:grid;grid-template-columns:76px minmax(0,1fr);gap:10px 14px;margin:0;padding:4px 2px 0;font-size:13px}
.kv dt{color:var(--sec)}
.kv dd{margin:0;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.kv dd.wrap{white-space:normal;word-break:break-all}
.detail-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:16px}
.split>.panel:only-child{grid-column:1/-1}

/* 新建任务 */
.create-panel{margin-top:0}
.create-grid{display:grid;grid-template-columns:minmax(220px,1fr) auto auto;gap:16px;align-items:end}
.create-grid>md-filled-button{white-space:nowrap;--md-filled-button-container-height:48px}
.field-label{display:block;color:var(--sec);font-size:13px;font-weight:650;margin-bottom:6px}
.plat-grid{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0}
md-chip-set{--md-chip-set-space:8px}
md-filter-chip{--md-filter-chip-container-height:36px}
.hint{display:flex;align-items:center;gap:7px;margin-top:12px;color:var(--sec);font-size:13px}
.hint:before{content:"i";flex:none;width:15px;height:15px;display:grid;place-items:center;border:1px solid var(--outl);border-radius:50%;font:700 9px/1 ui-monospace,monospace;color:var(--pri)}
.hint.warn{color:var(--err)}
.form-help{margin:8px 2px 0;color:var(--sec);font-size:12px}
.inline-error{margin-top:12px;padding:9px 11px;border:1px solid rgba(255,180,171,.3);border-radius:9px;background:rgba(147,0,10,.16);color:var(--err);font-size:12px}

/* 筛选条 */
.filter-bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.filter-bar md-outlined-text-field{width:220px;--md-outlined-text-field-top-space:8px;--md-outlined-text-field-bottom-space:8px}
.filter-bar md-outlined-select{width:150px;min-width:0}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:-2px 0 12px}

/* 日志 */
.log-console{min-width:0}
.log-tools{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.log-tools md-outlined-select{width:120px;min-width:0}
.log-tools md-checkbox{--md-checkbox-state-layer-size:32px;--md-checkbox-touch-target-size:0px}
.log-tools label{display:inline-flex;align-items:center;gap:4px;color:var(--sec);font-size:12px}
pre,.logs{height:370px;margin:0;padding:12px 14px;border:1px solid var(--outl-var);border-radius:12px;background:#050b0a;color:#a9bbb7;font-size:12px;line-height:1.65;overflow:auto;white-space:pre-wrap;word-break:break-word;box-shadow:inset 0 1px 14px rgba(0,0,0,.26)}
pre.nowrap,.logs.nowrap{white-space:pre}
.loading-state,.error-state{display:flex;align-items:center;justify-content:center;gap:12px;min-height:110px;padding:24px;color:var(--sec);text-align:center}
.error-state{color:var(--err);flex-wrap:wrap}

/* 文件 */
.files-panel{min-width:0}
.files{max-height:480px;overflow:auto}
.fgroup{margin-bottom:7px;padding:0}
.fgroup-head{display:flex;align-items:center;gap:8px;width:100%;min-height:40px;padding:8px 10px;border:1px solid var(--outl-var);border-radius:var(--s-sm);background:var(--surf-low);color:var(--on-pri-cont);font:inherit;font-size:12px;font-weight:700;cursor:pointer}
.fgroup-head:hover{border-color:var(--pri)}
.chevron{display:inline-block;font-size:9px;color:var(--pri);transition:transform var(--dur-s) var(--ease)}
.fgroup.open .chevron{transform:rotate(90deg)}
.fgroup-head .count{margin-left:auto}
.fgroup-head>span:nth-child(2){min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fgroup-body{display:none;padding:2px 0 2px 9px}
.fgroup.open .fgroup-body{display:block}
.file-row{display:flex;align-items:center;gap:10px;padding:9px 3px;border-bottom:1px solid var(--outl-var);font-size:12px}
.file-row.active .fname a{color:var(--pri)}
.fname{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fname a{color:var(--ter);text-decoration:none}
.fname a:hover{color:var(--pri)}
.fmeta{color:var(--sec);font-size:11px;white-space:nowrap}
.file-actions{display:flex;gap:6px;flex:none;align-items:center}
.load-more{display:block;width:100%;margin-top:10px}
.inline-player{margin-bottom:10px;border:1px solid var(--outl-var);border-radius:var(--s-md);background:var(--surf);overflow:hidden}
.inline-player-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;padding:10px 12px;background:var(--surf-low);border-bottom:1px solid var(--outl-var)}
.player-title{flex:1;min-width:0;font-size:12px;font-weight:650;color:var(--on-pri-cont);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.inline-player video{display:block;width:100%;max-height:52vh;background:#000}

/* Toast / 空态 */
.toast{position:fixed;right:24px;bottom:24px;z-index:70;max-width:min(420px,calc(100vw - 48px));padding:11px 16px;border:1px solid var(--outl-var);border-radius:var(--s-md);background:var(--surf-high);color:var(--on-pri-cont);font-size:13px;box-shadow:var(--shadow)}
.toast[hidden]{display:none}
.empty{display:flex;flex-direction:column;align-items:center;gap:6px;padding:36px 20px;border:1px dashed var(--outl-var);border-radius:16px;background:var(--surf-low);text-align:center}
.empty strong{color:var(--on-pri-cont);font-size:15px}
.empty span{font-size:13px;color:var(--sec)}
.empty md-outlined-button{margin-top:8px}

/* ── Material 按钮变体（MD3 没有 danger/紧凑密度，用 token 覆盖） ── */
md-filled-button.danger{
  --md-filled-button-container-color:var(--err);--md-filled-button-label-text-color:#3a0a06;
  --md-filled-button-hover-container-color:var(--on-err-cont);--md-filled-button-focus-container-color:var(--err);
}
md-text-button.danger,md-outlined-button.danger{
  --md-text-button-label-text-color:var(--err);--md-outlined-button-label-text-color:var(--err);
  --md-text-button-hover-label-text-color:var(--err);--md-outlined-button-hover-label-text-color:var(--err);
  --md-text-button-focus-label-text-color:var(--err);--md-outlined-button-focus-label-text-color:var(--err);
  --md-text-button-hover-state-layer-color:var(--err);--md-outlined-button-hover-state-layer-color:var(--err);
}
md-text-button.compact{--md-text-button-container-height:32px;--md-text-button-label-text-size:12px;padding:0 4px}
md-outlined-button.compact{--md-outlined-button-container-height:34px;--md-outlined-button-label-text-size:12px}
md-filled-button.compact{--md-filled-button-container-height:36px;--md-filled-button-label-text-size:12px}
md-icon-button.compact{--md-icon-button-state-layer-width:32px;--md-icon-button-state-layer-height:32px;--md-icon-button-icon-size:18px}

/* ── light DOM 组件：布局透明（见 docs/adr/0001）── */
app-header,app-nav,metric-card,task-card,task-list,task-filters,file-row,
overview-view,tasks-view,task-detail-view,library-view,new-task-view{display:contents}
app-icon{display:inline-flex}

@media(max-width:1100px){
  .workspace{grid-template-columns:160px minmax(0,1fr);gap:20px}
  .hero-monitor{flex-basis:200px;padding:18px}
  .hero{padding:24px;gap:20px}
  .create-grid{grid-template-columns:1fr}
}
@media(max-width:920px){
  .shell{padding:28px 20px calc(60px + env(safe-area-inset-bottom))}
  .workspace{grid-template-columns:1fr;gap:0}
  .topbar{margin-bottom:16px}
  .nav{position:static;width:100%;margin-bottom:20px}
  .nav md-list{display:flex;flex-direction:row;gap:4px;overflow:auto;padding:4px;border:1px solid var(--outl-var);background:var(--surf-low);border-radius:16px}
  .nav md-list-item{flex:1;min-width:max-content}
  .nav-label,.nav-note{display:none}
  .stats{grid-template-columns:repeat(2,minmax(0,1fr))}
  .split{grid-template-columns:1fr;gap:0}
  .split>.panel{margin-top:18px}
  .job{grid-template-columns:42px minmax(0,1fr)}
  .logo{width:42px;height:42px}
  .actions{grid-column:2;justify-content:flex-start;overflow-x:auto}
}
@media(max-width:680px){
  .shell{padding:24px 16px calc(56px + env(safe-area-inset-bottom))}
  .topbar{top:8px;padding:10px 12px;border-radius:18px}
  .panel{padding:18px}
  .panel-title{align-items:flex-start;flex-direction:column}
  .filter-bar{width:100%}
  .filter-bar md-outlined-text-field{width:100%;flex:1}
  .filter-bar md-outlined-select{flex:1;min-width:130px}
  .hero{padding:22px;gap:20px}
  .hero-monitor{flex-basis:100%;padding:16px 18px;display:grid;grid-template-columns:1fr auto;align-items:center;gap:12px}
  .monitor-value{grid-column:2;grid-row:1/3;margin:0}
  .hero-num{font-size:40px}
  .hero-actions{width:auto;margin-top:20px}
  .dist{grid-template-columns:repeat(2,minmax(0,1fr))}
  .stat{min-height:132px;padding:16px}
  .create-grid{grid-template-columns:1fr}
}
@media(max-width:440px){
  .shell{padding:20px 12px calc(48px + env(safe-area-inset-bottom))}
  .topbar{gap:8px;padding:12px 10px}
  .brand-mark{width:32px;height:36px;border-radius:11px}
  .brand-mark:before{left:6px}
  .brand-mark:after{left:7px;width:18px}
  h1{font-size:17px}
  .eyebrow{font-size:9px}
  .sub{display:none}
  .clock-pill{display:none}
  .status-pill{padding:0 8px;font-size:10px}
  .hero{padding:20px;border-radius:20px}
  .hero-copy h2{font-size:23px}
  .hero-num{font-size:34px}
  .panel{padding:16px;border-radius:18px}
  .stat{padding:14px;border-radius:14px}
  .stat b{font-size:24px}
  .job{grid-template-columns:38px minmax(0,1fr);gap:10px;padding:13px 11px}
  .logo{width:38px;height:38px;border-radius:10px}
  .actions{grid-column:1/-1}
  .file-row{flex-wrap:wrap}
  .fmeta{width:100%}
  pre,.logs{height:320px}
  .toast{right:12px;bottom:12px;left:12px;max-width:none;text-align:center}
}
@media(prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}
  .job:hover,.stat:hover{transform:none}
}
`;

export const sharedStyles = css`${unsafeCSS(cssText)}`;

if (typeof CSSStyleSheet === "function") {
  try {
    const sheet = new CSSStyleSheet();
    sheet.replaceSync(cssText);
    document.adoptedStyleSheets = [...document.adoptedStyleSheets, sheet];
  } catch (_) {
    /* 不支持构造样式表时由 index.html 的预渲染样式兜底 */
  }
}
