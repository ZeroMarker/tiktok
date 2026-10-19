# ADR 0001：WebUI 前端采用 Lit（原生 Web Components），去掉构建链

- 状态：已采纳
- 日期：2026-10-19（同日修订：lit 改走 CDN + 本地回落；组件改为 shadow/light DOM 混用）
- 范围：`webui/`（直播录制中心 WebUI）。`bili/webui/` 本来就是手写原生页面，不受影响。

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

### 2. lit@3：CDN 优先，仓库内 vendor 回落

`index.html` 在加载入口模块前用一段引导脚本注入 import map（import map 必须在任何 module
script 之前存在）：

- **正常网络**：`{"lit": "https://esm.sh/lit@3.3.3"}` —— esm.sh 会把 lit 内部的裸模块名
  （`lit-html`、`@lit/reactive-element`、`lit-element/lit-element.js`）改写成绝对 URL，
  所以 CDN 侧只需一条映射。
- **离线或 CDN 不可达**（内网/受限网络；探针 1.5 s 超时或 `navigator.onLine === false`）：
  回落到 `webui/vendor/`（[该目录的说明](../../webui/vendor/README.md)），它是 lit 浏览器运行时闭包的**最小集**，只有 6 个文件
  （lit 3.3.3 / lit-element 4.2.2 / lit-html 3.3.3 / @lit/reactive-element 2.1.2）。
- `sw.js` 同时缓存 CDN（`esm.sh`）模块与 vendor 闭包，因此**联网首访后即可离线打开**；
  vendor 文件列表与磁盘一致由单元测试保证，避免回落路径缺文件。

这样既用上了 CDN（版本集中、仓库不背依赖），又保住了 README 承诺的离线/内网可用性。

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
- 新增网络依赖：lit 从 `esm.sh` 加载（仅首个未缓存访问需要网络；之后由 SW/HTTP 缓存服务）。
  若部署环境要求完全离线、不接受任何外联，把 `index.html` 的 cdn map 去掉即可（引导脚本
  会固定走 vendor 分支）。
- 未改动后端 API 与业务逻辑；未修复设计规范 §9 记录的历史文案（`systemd 单元列表`、
  `Journal`、`最长 30 秒`）——仍按规范作为后续验收项。

## 验证

- `python3 -m unittest tests.test_webui`（71 用例）：静态目录（含穿越防护）、两张 import map
  （cdn 必须 https；vendor 目标必须存在）、前端源码只引用 cdn 覆盖的裸模块名、vendor 闭包
  自洽、SW 预缓存列表 = 磁盘 vendor 文件、`@event=${this.#handler}` 同文件定义。
- 无头 Chromium 实拍 `/`、`/#/tasks`、`/#/library`、`/#/new`、`/#/tasks/<unit>` 与 400px 窄屏，
  与改造前一致；控制台无脚本错误。
- 两条 lit 来源都实测：正常网络注入 `https://esm.sh/lit@3.3.3`；用
  `--host-resolver-rules="MAP esm.sh 127.0.0.1"` 模拟被墙/离线时注入 vendor map，页面同样正常。
- `curl` 校验 `/frontend/main.js`、`/vendor/lit/index.js` 以 JS MIME 返回；
  `/frontend/../server.py`、`/vendor/lit/LICENSE`、`/frontend/` 均 404。
