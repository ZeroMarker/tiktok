# bili/webui/vendor — 前端依赖（纯本地，无 CDN）

> 与录制中心 `webui/vendor/` 是**同一份文件**（git 按内容去重，不额外占仓库体积）。
> bili 管理页是独立服务，不跨目录引用；升级时两处一起换，`bili/tests/test_webui.py` 校验二者一致。

前端没有构建链，依赖以标准 ESM 文件随仓库提交，由 `index.html` 的**静态 import map**
映射裸模块名。运行期不访问任何 CDN（原因见 [ADR 0001](../../../docs/adr/0001-webui-frontend-lit.md#2-依赖全部本地-vendor无-cdn)）。

| 包 | 版本 | 目录 | 说明 |
| --- | --- | --- | --- |
| [`lit`](https://www.npmjs.com/package/lit) | 3.3.3 | `lit/` | 含 `decorators.js`、`directives/*`（Material Web 用到） |
| `lit-element` | 4.2.2 | `lit-element/` | |
| `lit-html` | 3.3.3 | `lit-html/` | |
| `@lit/reactive-element` | 2.1.2 | `reactive-element/` | |
| [`@material/web`](https://www.npmjs.com/package/@material/web) | 2.5.0 | `material-web/` | MD3 组件，见 [ADR 0004](../../../docs/adr/0004-material-web-controls.md) |
| `tslib` | 2.8.1 | `tslib/` | Material Web 的运行时辅助 |

每个包保留上游 `LICENSE`（lit 系列 BSD-3-Clause，Material Web Apache-2.0）。

## 只保留运行所需文件

- 不含 `.d.ts` / `*.js.map` / `development/` / `node/` / `sass`；
- `material-web/` 只含**用到的组件闭包**（127 个文件），不是完整包（完整包 2169 个文件）；
- `lit/` 含完整的 `directives/`、`decorators/`，因为 Material Web 会 `import "lit/decorators.js"`、
  `lit/directives/class-map.js` 等。

## 约束（由测试强制）

- import map 的每个目标都必须存在（`FrontendModuleGraphTest.test_shell_assets_exist`）；
- 前端与 vendor 源码里的裸模块名都必须能被 import map 解析
  （`test_bare_imports_are_mapped`）；
- vendor 内部的相对导入必须可解析（`test_relative_imports_resolve`）；
- 壳与前端源码不得出现 CDN 域名（`test_no_cdn_references`）；
- Material Web 的关键组件文件必须在位（`test_material_components_are_vendored`）。

## 更新步骤

不要 `npm install` 到仓库里；在临时目录取运行时闭包：

```bash
cd /tmp && mkdir -p wv && cd wv
for pkg in lit@3.3.3 lit-element@4.2.2 lit-html@3.3.3 @lit/reactive-element@2.1.2 \
           @material/web@2.5.0 tslib@2.8.1; do
  name="${pkg%@*}"; url="https://registry.npmjs.org/${name}/-/${name}-${pkg#*@}.tgz"
  file="$(echo "$name" | tr '/@' '__').tgz"; mkdir -p "$name"
  curl -sL -o "$file" "$url" && tar xzf "$file" -C "$name" --strip-components=1
done
```

1. `lit*`：复制 `.js`（排除 `development/`、`node/`、`*.map`、`*.d.ts`），保持目录结构；
2. `@material/web`：只复制**用到的组件闭包**——从 `material.js` 里的入口出发，沿相对
   `import`/`from` 递归（单双引号都要匹配），得到文件清单；
3. `tslib`：`tslib.es6.js` + `LICENSE.txt`；
4. 更新 `index.html` 的 import map（如版本目录有变）、本 README 的版本表、ADR 0001/0004；
5. 同步到 `webui/vendor/`，跑 `bash test.sh`。

## Material Symbols 图标

`material-symbols/` 保存两套管理界面共用的官方 Rounded SVG 路径子集（含导航填充态）。
固定上游版本、参数和更新方法见 [material-symbols/README.md](material-symbols/README.md)，
采用 Apache-2.0 许可，本地加载，无字体或 CDN 请求。两处副本须同步更新。
