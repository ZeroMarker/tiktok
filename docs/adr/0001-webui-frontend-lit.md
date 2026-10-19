# ADR 0001：WebUI 前端采用 Lit（原生 Web Components），去掉构建链

- 状态：已采纳
- 日期：2026-10-19（同日修订：依赖改为纯本地 vendor，移除 CDN；组件 shadow/light DOM 混用；
  控件层迁移到 @material/web 见 [ADR 0004](0004-material-web-controls.md)）
- 范围：`webui/`（直播录制中心 WebUI）。`bili/webui/` 后来也按同一方案迁移，见 [ADR 0006](0006-bili-webui-lit.md)。

## 背景

技术选型要求（详见《技术选型约束》）：

- 前端用原生 Web（HTML / CSS / JavaScript），**不引入 Node.js 运行时及其构建链**（不用 npm / bundler）；
- 前端框架路线是 **Lit**：`class extends LitElement` + `customElements.define()`，ESM 引入
  （**CDN / import map / 本地 vendor**），**不用装饰器**，响应式属性用 `static properties`，
  样式用 `static styles` + `css` 标签模板；
- 既有项目与选型冲突时，先说明冲突点、给出改造方案，确认后再动手。

## 冲突点（改造前）

1. **构建链**：`webui/frontend/` 是 Vue 3 + Vite + npm 工程（`package.json`、`vite.config.js`、
   `vite-plugin-singlefile`），前端无法脱离 Node 修改。
2. **产物耦合后端包**：`npm run build` 把 `dist/index.html` 复制成 `webui/index.html`（151 KB
   单文件构建产物），直接落在后端 Python 包目录里，由 `webui/server.py` 服务；
   `.github/workflows/checks.yml` 还有「重建后零 diff」的强制校验。
3. 由此产生的次级耦合：接口契约（`/api/*` 字符串）在 `server.py` 与前端里各写一遍；前端只能同源
   访问（相对路径 + 无鉴权/CORS），且构建产物必须与源码一起提交。

## 决策

### 1. 去掉构建链：原生 ESM + import map

- 前端为**原生 Web Components + Lit 3**，`webui/index.html` 退化为静态壳页面，
  入口模块 `./frontend/main.js`，前端源码即产物（`webui/frontend/`）。
- 删除 npm / Vite / `package.json` / `node_modules` / 构建产物与对应 CI job。
- 后端新增受控静态目录（`/frontend/`、`/vendor/`）：白名单后缀 + 强制目录边界（防穿越）。

### 2. 依赖全部本地 vendor（无 CDN）

`index.html` 使用**静态 import map**，所有裸模块名直接指向仓库内 `webui/vendor/`：

```json
{
  "lit": "./vendor/lit/index.js",
  "lit/": "./vendor/lit/",
  "lit-element": "./vendor/lit-element/lit-element.js",
  "lit-element/": "./vendor/lit-element/",
  "lit-html": "./vendor/lit-html/lit-html.js",
  "lit-html/": "./vendor/lit-html/",
  "@lit/reactive-element": "./vendor/reactive-element/reactive-element.js",
  "@lit/reactive-element/": "./vendor/reactive-element/",
  "@material/web/": "./vendor/material-web/",
  "tslib": "./vendor/tslib/tslib.es6.js"
}
```

内容：lit 3.3.3 / lit-element 4.2.2 / lit-html 3.3.3 / @lit/reactive-element 2.1.2、
`@material/web` 2.5.0（按需组件闭包）、tslib 2.8.1。更新步骤与文件清单见
[webui/vendor/README.md](../../webui/vendor/README.md)。

**为什么最终不用 CDN。** 早期实现是「CDN（esm.sh）优先 + vendor 回落」，实测发现三个问题：

1. **双份 lit 风险**：esm.sh 会把 Material Web 内部的 `lit`/`lit/decorators.js` 改写成
   它自己的绝对 URL。虽然 `?external=lit` 对子图有效，但需要为**每个入口**带上参数，
   漏一个就会出现两份 `LitElement`（两套样式表与控制器，`instanceof` 失效）——这类 bug
   极难定位。
2. **请求放大**：esm.sh 每个模块先返回一个转发 stub，真正的 `.mjs` 再请求一次；而后端
   `BaseHTTPRequestHandler` 默认是 HTTP/1.0（无 keep-alive），模块数一多就是几十条连接。
3. **可用性与确定性**：内网/被墙时整页打不开；CDN 侧还会按 `^2.1.0` 之类的范围解析传递
   依赖，版本可能漂移。

本地 vendor 的体积很小（未压缩总计约 1.6 MB，其中只用到的 Material 组件闭包 558 KB），
换来的是：单一 lit 实例、零跨域请求、离线可用、版本可审计（含 LICENSE）、CI 可校验。

### 2.1 控件层使用 @material/web

见 [ADR 0004](0004-material-web-controls.md)：按钮/输入/下拉/复选/对话框/标签使用 MD3
组件，外观通过 `--md-sys-color-*` 等 token 桥接；布局与自有卡片保持原样。

### 3. Shadow DOM 与 light DOM 混用

原则：**要参与父级布局或级联的组件用 light DOM，自包含的组件用 shadow DOM。**

- **light DOM**（`LightElement extends BaseElement`，`createRenderRoot(){return this}`）：
  `app-header`、`app-nav`、`app-icon`、`metric-card`、`task-card`、`task-list`、`task-filters`、
  `task-creation-form`、`file-row`、五个 view。它们的样式来自所在地的共享样式表
  （`frontend/styles.js`），因此祖先选择器（`.offline .status-pill`、`.create-panel .plat-grid`、
  `metric-card:nth-child(n) .stat`）与父布局（`.jobs` 网格项、`.page-content` 子元素、
  sticky 的 `.topbar`/`.nav`）都照常生效，不再需要 `:host` 变通与规则搬迁。
- **shadow DOM**（默认 `BaseElement`）：`app-root`（外壳，设计系统的封装边界）、
  `connection-banner`、`global-feedback`、`log-panel`、`file-browser`、`file-group`、
  `file-toolbar`、`media-player` —— 这些组件自带完整样式，无祖先依赖。
- 需要「布局透明」的 light DOM 宿主（`display:contents`）与指标卡位置配色等结构性规则，
  集中在 `frontend/styles.js` 里用元素名表达；这是本次唯一进入设计系统的结构性约定。

效果：整棵应用树落在 `app-root` 的 shadow root 内（设计系统不泄漏到宿主页面），内部默认是
light DOM 的普通级联，只有真正自包含的部件再开一层 shadow root。

## 结果与取舍

- 状态层：`stores/store.js` 提供 `createStore()`（深层 Proxy + 微任务合并通知），保留原先
  `state.x = y` 的写法；`base.js` 的 `BaseElement` 订阅 store，变更即 `requestUpdate()`。
- 事件：组件对外 `dispatchEvent(new CustomEvent(type, {bubbles:true, composed:true}))`，
  跨 shadow 边界直接冒泡到使用方，不做手工中转。
- 依赖随仓库提交（含 LICENSE），升级需按 `webui/vendor/README.md` 手动换文件；
  运行期**不访问公网**，离线/内网可用。
- 未改动后端 API 与业务逻辑；未修复设计规范 §9 记录的历史文案（`systemd 单元列表`、
  `Journal`、`最长 30 秒`）——仍按规范作为后续验收项。

## 验证

- `python3 -m unittest tests.test_webui`：静态目录（含穿越防护）、静态 import map 目标全部存在、
  前端与 vendor 源码的裸模块名都能被映射、相对导入可解析、壳与前端源码不出现 CDN 域名、
  Material 组件已 vendor、SW 预缓存目标存在、`@event=${this.#handler}` 同文件定义。
- 无头 Chromium 实拍 `/`、`/#/tasks`、`/#/library`、`/#/new`、`/#/tasks/<unit>` 与 400px 窄屏，
  与改造前一致；控制台无脚本错误。
- 纯 vendor 加载实测：无头浏览器逐条 `import("@material/web/…")` 全部成功；主页面零跨域请求、
  控制台无脚本错误。
- `curl` 校验 `/frontend/main.js`、`/vendor/lit/index.js` 以 JS MIME 返回；
  `/frontend/../server.py`、`/vendor/lit/LICENSE`、`/frontend/` 均 404。
