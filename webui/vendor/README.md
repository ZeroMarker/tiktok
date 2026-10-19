# webui/vendor — lit@3 的本地回落（fallback）

前端无构建链，lit@3 的引入方式见 [ADR 0001](../docs/adr/0001-webui-frontend-lit.md)：

1. **默认走 CDN**：`index.html` 的引导脚本注入 `{"lit": "https://esm.sh/lit@3.3.3"}`；
2. **离线 / CDN 不可达时回落到本目录**：探针超时（1.5 s）或 `navigator.onLine === false`
   时改用这里的 import map。

这里只放 lit 浏览器运行时的**最小闭包**（6 个文件，未压缩，便于审查），不是完整包：

| 文件 | 来自 | 版本 |
| --- | --- | --- |
| `lit/index.js` | [`lit`](https://www.npmjs.com/package/lit) | 3.3.3 |
| `lit-element/lit-element.js` | `lit-element` | 4.2.2 |
| `lit-html/lit-html.js`、`lit-html/is-server.js` | `lit-html` | 3.3.3 |
| `reactive-element/reactive-element.js`、`reactive-element/css-tag.js` | `@lit/reactive-element` | 2.1.2 |

每个目录保留上游 `LICENSE`（BSD-3-Clause）。没有 `lit/directives/*` 与 `decorators/`：
本应用只用 `html` / `css` / `LitElement` / `nothing` 等核心导出，且**不使用装饰器**。

## 约束

- `sw.js` 的 `ASSETS` 必须预缓存上面全部 `.js`（离线回落才能生效）；这一致性由
  `tests/test_webui.py::FrontendModuleGraphTest::test_service_worker_precaches_the_vendor_fallback`
  强制。
- 前端源码只允许引用 CDN map 覆盖的裸模块名（目前只有 `lit`），由
  `test_bare_imports_are_mapped` 强制。

## 更新步骤

不要 `npm install` 到仓库里；只取出运行时闭包：

```bash
cd /tmp && mkdir -p lit-vendor && cd lit-vendor
for pkg in lit@3.3.3 lit-element@4.2.2 lit-html@3.3.3 @lit/reactive-element@2.1.2; do
  name="${pkg%@*}"; url="https://registry.npmjs.org/${name}/-/${name}-${pkg#*@}.tgz"
  curl -sL -o "$(echo "$name" | tr '/@' '__').tgz" "$url" && mkdir -p "$name" && tar xzf "$(echo "$name" | tr '/@' '__').tgz" -C "$name" --strip-components=1
done
```

复制上面表格里的 6 个文件与 4 个 `LICENSE` 到本目录，然后：

1. 同步 `index.html` 的 cdn/vendor import map（版本号）、`sw.js` 的 `ASSETS`、
   本 README 的版本表与 ADR 0001；
2. 跑 `python3 -m unittest tests.test_webui`。
