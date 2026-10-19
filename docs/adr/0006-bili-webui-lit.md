# ADR 0006：Bili 管理页前端迁到 Lit + Material Web

- 状态：已采纳
- 日期：2026-10-19
- 范围：`bili/webui/`（前端 + 静态路由），后端 `/api/*` 契约不变
- 相关：[ADR 0001](0001-webui-frontend-lit.md)（Lit、无构建链、纯本地 vendor）、
  [ADR 0004](0004-material-web-controls.md)（@material/web 控件层）、
  [ADR 0005](0005-bili-monitord-split.md)（值守拆为后端服务）

## 背景

录制中心 WebUI 已经是 Lit + @material/web，Bili 管理页还是一个 580 行的单文件页面：
内联样式加内联脚本，`getElementById` 手工改 DOM，控件都是自己写的。两套前端写法不一样，
维护时得在两种心智模型之间切换。

## 决策

照搬录制中心的方案，后端接口一行不改：

```
bili/webui/
  index.html            静态壳：静态 import map + <bili-app>
  frontend/
    main.js             入口：注册组件、挂全局样式、10s 轮询、注册 SW
    store.js            共享状态（status / online / busy / notice / toast），极简发布订阅
    api.js              /api/* 封装
    actions.js          用户操作串行执行（busy）、统一提示、操作后刷新
    base.js             BaseElement（订阅 store，light DOM）、本地草稿
    ui.js               图标、按钮转圈、确认对话框等共用片段
    styles.js           全局样式表：浅/深色调色板 → --md-sys-* token 桥接 + 布局
    material.js         用到的 Material 组件集中注册
    components/         bili-app、status-card、live-card、replay-card、room-card、logs-card
  vendor/               lit 3.3.3 / @material/web 2.5.0 / tslib 2.8.1（纯本地）
```

- **全部 light DOM**：只有一张全局样式表（`document.adoptedStyleSheets`），桌面端「左侧状态卡
  sticky、右侧四张卡」的网格规则可以直接作用到各个卡片组件上。Material 组件自带 shadow DOM，
  外观只通过 `--md-*` token 定制。
- **控件对应**：按钮 → `md-filled-button`（tonal / danger 用 token 覆盖）/ `md-outlined-button`；
  输入框和多行文本 → `md-outlined-text-field`；下拉框 → `md-outlined-select`；复选框 → `md-checkbox`；
  `window.confirm` → `md-dialog`（自带焦点陷阱，支持 Escape 关闭）；进度条 → `md-linear-progress`；
  按钮上的转圈 → `md-circular-progress`。
- **保留旧行为**：表单草稿（localStorage 键仍是 `bili-form-v1`，旧草稿能直接读出来）、回车提交、
  后台标签页暂停轮询、日志在底部时自动跟随新内容、值守复选框在操作失败后回滚到后端的真实状态、
  浅色/深色主题跟随系统。
- **vendor 与录制中心是同一份文件**：bili 是独立服务，不跨目录引用 `../webui/vendor`；
  git 按内容去重，所以复制一份不会增加仓库体积。测试会校验两边逐字节一致，升级时漏同步一边就会失败。
- **静态路由**：后端新增 `/frontend/`、`/vendor/` 两个路由，只放行 `.js/.css/.svg`，并做了目录穿越防护。
- **Service Worker**（`bili-push-v4`）：`/vendor/*` 版本固定，缓存优先；壳页面和 `/frontend/*`
  网络优先、离线时回退到缓存，改完前端刷新一下就生效；`/api/*` 不经过缓存。

## 取舍

- 首屏要加载 lit 和 Material 组件闭包（本地约 0.6 MB，之后走 SW 缓存）；旧版单文件页面约 36 KB。
- MD3 控件的默认密度比旧版高（输入框 56px），手机上页面会更长。
- 文件选择仍用原生 `<input type="file">`，因为 MD3 Web 没有对应组件。toast 也是自己写的，
  因为 MD3 Web 没有 snackbar 组件。
