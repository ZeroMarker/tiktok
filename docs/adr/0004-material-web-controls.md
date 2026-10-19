# ADR 0004：控件层迁移到 @material/web（MD3）

- 状态：已采纳
- 日期：2026-10-19
- 范围：`webui/frontend/`、`webui/vendor/material-web/`
- 相关：[ADR 0001](0001-webui-frontend-lit.md)（Lit + 无构建链 + 纯 vendor）

## 背景

前端原本是「Lit + 自写控件」（`<button>`、`<input>`、`<select>`、自写 modal/分段选择），
要求迁移到现成组件库。选型规则允许在 Lit 之上按需选用 Web Components 控件库，
`@material/web` 是其中之一。

取舍基线：**同等实现即可，不要求像素还原**；但交互与无障碍不能退化。

## 决策

使用 `@material/web` 2.5.0 的 MD3 组件替换**交互原语**，布局与自有展示组件保持原样：

| 原实现 | 现在 |
| --- | --- |
| `<button class="secondary/danger/mini">` | `md-text-button` / `md-outlined-button` / `md-filled-button`（`.danger`、`.compact` 用 token 覆盖） |
| `<input>`（搜索、频道） | `md-outlined-text-field` |
| `<select>`（状态/直播/平台/日志行数） | `md-outlined-select` + `md-select-option` |
| `<input type="checkbox">` | `md-checkbox` |
| 自写 `.modal` + 手写聚焦 | `md-dialog`（原生 `<dialog>` + `showModal()`，自带焦点陷阱与 Escape） |
| 平台卡 / 画质分段 / 平台筛选 chip / 库页分段 | `md-filter-chip` + `md-chip-set` |
| 侧栏导航按钮 | `md-list` + `md-list-item` |
| 磁盘占用自写进度条 | `md-linear-progress` |

保持不变（没有对应 MD3 组件，或属于展示结构）：`.topbar` 品牌区、`metric-card`、任务行
（`.job`）、文件树（`.fgroup`）、日志 `<pre>`、Toast、状态徽标、平台分布卡。

## 主题

MD3 组件只读 `--md-sys-color-*` 等 token（自定义属性可穿透 shadow 边界）。`styles.js`
把原调色板映射成一套深色方案：

```css
--md-sys-color-primary: var(--pri);         /* 薄荷绿 */
--md-sys-color-on-primary: var(--on-pri);
--md-sys-color-surface: var(--surf);
--md-sys-color-error: var(--err);
--md-dialog-container-color: var(--surf-cont);
/* …surface-container-* / outline / inverse-* / typescale 字体 */
```

因此组件外观跟原设计语言一致，但**尺寸采用 MD3 默认密度**（按钮 40px、输入框 56px），
比原来的紧凑后台界面更高——这是"不要求像素还原"的直接代价。

## 依赖与加载

Material Web 的入口文件用**相对路径**互相引用，所以只能整包 vendor（不能靠 CDN 改写）：

- `webui/vendor/material-web/`：所选组件的运行时闭包（127 个 `.js`，558 KB，Apache-2.0）；
- `webui/vendor/tslib/tslib.es6.js`：Material Web 的运行时辅助（2.8.1）；
- `webui/frontend/material.js`：集中 import 所有用到的组件，避免各处重复注册。

`index.html` 用静态 import map 把 `@material/web/` 与 `tslib` 指到本地；运行期零跨域请求。

## 后果

**收益**

- 无障碍与键盘行为来自组件实现：`md-dialog` 的焦点陷阱/还原、`md-select` 的方向键与
  类型 ahead、`md-outlined-text-field` 的 label/错误关联、`md-checkbox` 的 `aria-checked`。
  设计规范 §9 里「对话框焦点」「表单错误感知」两项由组件提供。
- 状态层、接口层、事件流完全未变：本次只改 `frontend/components`、`frontend/views`、
  `frontend/styles.js`、`index.html`、`vendor/`；`stores/`、`services/`、`api.js`、
  `router.js`、后端全部未动。

**代价与已知取舍**

- **密度变高**：MD3 控件比原先的紧凑排版大；筛选条与日志工具条在窄屏会换行更多。
- **没有 danger 变体**：用 token 覆盖出 `.danger`（红色文字/容器）。
- **没有 segmented button**（在 labs 里，未 vendor）：平台/画质用 `md-filter-chip` 表达单选，
  语义是"按钮组"而非 `radiogroup`；Tab 可逐项聚焦，但没有 roving tabindex。
- **仍然自写**：Toast（MD3 Web 没有 snackbar）、分组折叠头、任务行/文件行的展示结构。
- **`@material/web` 的 `md-outlined-text-field` 不转发 `input` 事件**（内部 `handleInput`
  只更新 `value`）——好在 `InputEvent` 是 composed 的，监听宿主上的 `@input` 仍能收到
  （同类组件都按此模式使用，见 `task-filters.js`）。

## 验证

- 单测：`tests/test_webui.py`（81 用例）含"Material 组件已 vendor""import map 目标全部存在"
  "前端与 vendor 裸模块名可映射""壳与源码不出现 CDN 域名"。
- 无头 Chromium 实拍：概览 / 任务 / 任务详情 / 录制文件 / 新建任务 + 400 CSS px 窄屏；
  退出确认框单独验证（`md-dialog` 渲染、按钮与遮罩正常）。
- 关键 API 实测：`md-outlined-text-field` 的 `input/keyup/change` 可穿出、`md-outlined-select`
  的 `value` 与选项、`md-filter-chip` 点击切换 `selected`。
