// styles.js — 全局样式表（挂到 document.adoptedStyleSheets，组件全是 light DOM）。
//
//   1) 调色板（浅色 / 深色跟随系统）+ MD3 token 桥接：Material 组件只读 --md-sys-*
//   2) 布局与自有展示结构（顶栏、卡片、服务块、徽标、日志台、toast）
//   3) Material 组件的少量尺寸 / 变体覆盖（danger 按钮、紧凑复选框）
import { css } from "lit";

export const globalStyles = css`
:root{
  color-scheme:light dark;
  --primary:#4f46e5; --on-primary:#fff;
  --primary-container:#e9e7ff; --on-primary-container:#27216f;
  --secondary-container:#eef0f8; --on-secondary-container:#343746;
  --success:#17834f; --success-container:#e1f6e9; --on-success-container:#116039;
  --surface:#f7f8fc; --surface-container-low:#fff; --surface-container:#f2f3f8;
  --surface-container-high:#eceef5; --surface-container-highest:#e3e6ef;
  --on-surface:#171923; --on-surface-variant:#636779;
  --outline:#777b8d; --outline-variant:#dfe1e9;
  --error:#c2353c; --on-error:#fff; --error-container:#ffeaeb; --on-error-container:#8c1d23;
  --shadow:0 1px 2px rgba(26,29,43,.05),0 8px 28px rgba(26,29,43,.06);
  --r-lg:22px; --r-md:16px; --r-sm:14px;
  --font:system-ui,-apple-system,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  --mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;

  /* ── MD3 token 桥接 ── */
  --md-sys-color-primary:var(--primary); --md-sys-color-on-primary:var(--on-primary);
  --md-sys-color-primary-container:var(--primary-container); --md-sys-color-on-primary-container:var(--on-primary-container);
  --md-sys-color-secondary:var(--on-surface-variant);
  --md-sys-color-secondary-container:var(--secondary-container); --md-sys-color-on-secondary-container:var(--on-secondary-container);
  --md-sys-color-error:var(--error); --md-sys-color-on-error:var(--on-error);
  --md-sys-color-error-container:var(--error-container); --md-sys-color-on-error-container:var(--on-error-container);
  --md-sys-color-surface:var(--surface); --md-sys-color-on-surface:var(--on-surface);
  --md-sys-color-on-surface-variant:var(--on-surface-variant); --md-sys-color-surface-variant:var(--surface-container-high);
  --md-sys-color-surface-container-lowest:var(--surface-container-low);
  --md-sys-color-surface-container-low:var(--surface-container-low);
  --md-sys-color-surface-container:var(--surface-container);
  --md-sys-color-surface-container-high:var(--surface-container-high);
  --md-sys-color-surface-container-highest:var(--surface-container-highest);
  --md-sys-color-outline:var(--outline); --md-sys-color-outline-variant:var(--outline-variant);
  --md-sys-color-inverse-surface:var(--on-surface); --md-sys-color-inverse-on-surface:var(--surface);
  --md-sys-color-shadow:#000; --md-sys-color-scrim:#000;
  --md-sys-typescale-body-large-font:var(--font);
  --md-sys-typescale-body-medium-font:var(--font);
  --md-sys-typescale-label-large-font:var(--font);
  --md-sys-typescale-title-large-font:var(--font);
  --md-sys-typescale-headline-small-font:var(--font);
  --md-dialog-container-color:var(--surface-container-low);
  --md-menu-container-color:var(--surface-container-low);
  --md-focus-ring-color:var(--primary);
}
@media (prefers-color-scheme:dark){
  :root{
    --primary:#b8b3ff; --on-primary:#211a83;
    --primary-container:#302b75; --on-primary-container:#e8e6ff;
    --secondary-container:#282b34; --on-secondary-container:#e1e3ec;
    --success:#56d694; --success-container:#173d2b; --on-success-container:#8aebb5;
    --surface:#111318; --surface-container-low:#181a20; --surface-container:#1d2027;
    --surface-container-high:#262932; --surface-container-highest:#30343e;
    --on-surface:#eef0f7; --on-surface-variant:#aeb2c0;
    --outline:#858999; --outline-variant:#343741;
    --error:#ffb3b7; --on-error:#601410; --error-container:#50151a; --on-error-container:#ffdadb;
    --shadow:0 1px 2px rgba(0,0,0,.22),0 12px 32px rgba(0,0,0,.18);
  }
}
html{-webkit-text-size-adjust:100%}
*{box-sizing:border-box}
[hidden]{display:none!important}
body{font-family:var(--font);margin:0;color:var(--on-surface);background:var(--surface);
  min-height:100vh;min-height:100dvh;overflow-x:clip}
body::before{content:"";position:fixed;inset:0 0 auto;height:360px;pointer-events:none;z-index:-1;
  background:radial-gradient(circle at 15% 0,color-mix(in srgb,var(--primary) 12%,transparent),transparent 48%),
             radial-gradient(circle at 90% 5%,color-mix(in srgb,#45b7a3 9%,transparent),transparent 38%)}
bili-app,status-card,live-card,replay-card,room-card,logs-card{display:block}

/* ── 顶栏 ── */
.topbar{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:12px;
  padding:12px max(20px,env(safe-area-inset-right)) 12px max(20px,env(safe-area-inset-left));
  padding-top:max(12px,env(safe-area-inset-top));
  background:color-mix(in srgb,var(--surface) 82%,transparent);
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border-bottom:1px solid var(--outline-variant)}
.topbar .logo{width:40px;height:40px;border-radius:12px;flex:none;display:grid;place-items:center;
  background:linear-gradient(145deg,var(--primary),#7c72ff);color:var(--on-primary);box-shadow:var(--shadow)}
.topbar h1{font-size:clamp(17px,4.5vw,20px);margin:0;font-weight:700;letter-spacing:.2px}
.topbar .sub{font-size:12px;color:var(--on-surface-variant)}
.spacer{flex:1}
.online{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:700;color:var(--on-surface-variant);
  padding:7px 11px;border:1px solid var(--outline-variant);border-radius:999px;background:var(--surface-container-low)}
.online::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--success);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--success) 15%,transparent)}
.online.offline{color:var(--error)}.online.offline::before{background:var(--error);box-shadow:none}

/* ── 页面网格 ── */
.wrap{max-width:1180px;width:min(100% - 40px,1180px);margin:0 auto;padding:28px 0 64px;display:flex;flex-direction:column;gap:16px}
.busy-bar{--md-linear-progress-track-height:4px;--md-linear-progress-active-indicator-height:4px;
  --md-linear-progress-track-shape:999px;width:100%;transition:opacity .2s}
.busy-bar.idle{opacity:0}
.notice{padding:12px 16px;border-radius:13px;font-size:13px;line-height:1.6;border:1px solid var(--outline-variant);
  background:var(--secondary-container);color:var(--on-secondary-container)}
.notice.error{background:var(--error-container);color:var(--error)}
.foot{text-align:center;font-size:12px;color:var(--on-surface-variant)}

/* ── 卡片 ── */
.card{background:var(--surface-container-low);border-radius:var(--r-lg);padding:20px;
  box-shadow:var(--shadow);border:1px solid var(--outline-variant)}
.card-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px}
.card-head h2{margin:0 0 4px;font-size:17px;font-weight:700;color:var(--on-surface);display:flex;align-items:center;gap:8px}
.card-head h2 svg{flex:none}
.card-kicker{font-size:12px;color:var(--on-surface-variant);line-height:1.5}
.card-head .pill{background:transparent;border:1px solid var(--outline-variant);letter-spacing:.5px}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:12px 0}
.row:last-child{margin-bottom:0}
.row>md-outlined-text-field,.row>md-outlined-select{flex:1;min-width:200px}
.row>.narrow{flex:0 1 190px;min-width:150px}
.hint{font-size:12px;color:var(--on-surface-variant);text-wrap:pretty;line-height:1.6}
.check{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--on-surface-variant);cursor:pointer}
.sub-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:16px}
.sub-label{font-size:12px;font-weight:700;color:var(--on-surface-variant);letter-spacing:.3px}

.mode-hero{display:flex;align-items:center;gap:14px;border-radius:var(--r-md);padding:20px;
  background:linear-gradient(135deg,var(--primary-container),var(--surface-container));
  border:1px solid color-mix(in srgb,var(--primary) 24%,var(--outline-variant))}
.mode-dot{width:14px;height:14px;border-radius:50%;background:var(--outline);flex:none}
.mode-dot.on{background:#2e7d32;box-shadow:0 0 0 6px color-mix(in srgb,#2e7d32 22%,transparent);animation:pulse 1.6s infinite}
.mode-dot.warn{background:#b26a00;box-shadow:0 0 0 6px color-mix(in srgb,#b26a00 22%,transparent);animation:pulse 1.6s infinite}
@keyframes pulse{50%{box-shadow:0 0 0 9px transparent}}
.mode-name{font-size:clamp(19px,5.5vw,22px);font-weight:800}
.svc{flex:1;min-width:220px;background:var(--surface-container);border:1px solid var(--outline-variant);
  border-radius:var(--r-md);padding:14px}
.svc .t{font-size:13px;font-weight:700;display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.svc .s{font-size:12px;color:var(--on-surface-variant);margin-top:4px;font-variant-numeric:tabular-nums;word-break:break-all}
.pill{display:inline-block;padding:3px 9px;border-radius:999px;font-size:11px;font-weight:700;
  background:var(--surface-container-highest);color:var(--on-surface-variant)}
.pill.live{background:var(--success-container);color:var(--on-success-container)}
.pill.bad{background:var(--error-container);color:var(--error)}
pre{background:var(--surface-container-high);color:var(--on-surface);border-radius:var(--r-md);
  padding:14px 16px;overflow:auto;max-height:320px;font-size:12px;line-height:1.6;
  white-space:pre-wrap;margin:10px 0 0;font-family:var(--mono);scrollbar-width:thin}
.cover-preview{width:96px;height:64px;object-fit:cover;border-radius:12px;border:1px solid var(--outline-variant);
  background:var(--surface-container-high)}
.file-pick{display:flex;flex-direction:column;gap:6px;flex:1;min-width:200px}
.file-pick input[type=file]{font:inherit;font-size:13px;color:var(--on-surface-variant)}
.file-pick input[type=file]::file-selector-button{font:inherit;font-size:13px;font-weight:700;margin-right:10px;
  padding:8px 14px;border:none;border-radius:999px;background:var(--secondary-container);
  color:var(--on-secondary-container);cursor:pointer}

/* ── Material 覆盖 ── */
md-filled-button,md-outlined-button,md-text-button{white-space:nowrap}
md-filled-button.danger{--md-filled-button-container-color:var(--error-container);
  --md-filled-button-label-text-color:var(--error);--md-filled-button-hover-label-text-color:var(--error);
  --md-filled-button-focus-label-text-color:var(--error);--md-filled-button-pressed-label-text-color:var(--error);
  --md-filled-button-icon-color:var(--error)}
md-filled-button.tonal{--md-filled-button-container-color:var(--secondary-container);
  --md-filled-button-label-text-color:var(--on-secondary-container);--md-filled-button-hover-label-text-color:var(--on-secondary-container);
  --md-filled-button-focus-label-text-color:var(--on-secondary-container);--md-filled-button-pressed-label-text-color:var(--on-secondary-container);
  --md-filled-button-icon-color:var(--on-secondary-container);--md-filled-button-container-elevation:0;
  --md-filled-button-hover-container-elevation:0}
md-circular-progress[slot=icon]{--md-circular-progress-size:18px;--md-circular-progress-active-indicator-color:currentColor}
md-checkbox{--md-checkbox-state-layer-size:32px}
md-outlined-text-field.mono{--md-outlined-text-field-input-text-font:var(--mono);--md-outlined-text-field-input-text-size:13px}

/* ── toast ── */
.toast{position:fixed;left:50%;bottom:calc(24px + env(safe-area-inset-bottom));transform:translateX(-50%) translateY(80px);
  z-index:9;background:var(--on-surface);color:var(--surface);border-radius:var(--r-sm);padding:13px 20px;
  font-size:14px;max-width:min(92vw,560px);box-shadow:var(--shadow);opacity:0;transition:all .25s;cursor:pointer;
  border:none;font-family:inherit;text-align:left}
.toast.show{transform:translateX(-50%) translateY(0);opacity:1}
.toast.err{background:var(--error);color:var(--on-error)}

/* ── 响应式 ── */
@media(min-width:1000px){
  .wrap{display:grid;grid-template-columns:repeat(12,1fr);align-items:start}
  .wrap>.busy-bar,.wrap>.notice,.wrap>.foot{grid-column:1/-1}
  /* 状态卡占左侧 1~5 列、跨右侧四张卡的行区并 sticky：钉住整页又不会盖到右列卡片 */
  .wrap>status-card{grid-column:1/span 5;grid-row:span 4;position:sticky;top:92px;
    max-height:calc(100dvh - 108px);overflow-y:auto;border-radius:var(--r-lg)}
  .wrap>live-card,.wrap>replay-card,.wrap>room-card,.wrap>logs-card{grid-column:6/-1}
}
@media(min-width:641px) and (max-width:999px){ .wrap{width:min(100% - 40px,720px)} .svc{min-width:0} }
@media(max-width:640px){
  .wrap{gap:14px;padding-top:14px;width:min(100% - 24px,1180px)}
  .card{padding:16px}
  .card-head{display:block}.card-head .pill{margin-top:8px}
  .row{flex-direction:column;align-items:stretch}
  .row>*{width:100%;min-width:0}
  .row>.narrow{flex:none}
  .svc{min-width:0}
  pre{max-height:50dvh}
  .topbar{gap:10px;padding-left:max(12px,env(safe-area-inset-left));padding-right:max(12px,env(safe-area-inset-right))}
  .topbar .sub,.online{display:none}
  .mode-hero{flex-wrap:wrap}
}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important}}
`;
