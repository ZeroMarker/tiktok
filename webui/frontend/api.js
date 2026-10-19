// api.js — 轻量 fetch 封装：JSON、超时、错误提取。
// timeout 可按请求覆盖：停止/重启要等 systemd 收尾（服务端最长 35s）。
export async function api(url, opt = {}) {
  const { timeout = 12000, ...options } = opt;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const request = {
    ...options,
    headers: { ...(options.headers || {}), "Content-Type": "application/json" },
    signal: controller.signal,
  };
  try {
    const r = await fetch(url, request);
    let d = {};
    try {
      d = await r.json();
    } catch {
      /* 非 JSON 响应 */
    }
    if (!r.ok) throw Error(d.error || r.statusText);
    return d;
  } catch (e) {
    if (e.name === "AbortError") throw Error("请求超时，请稍后重试");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
