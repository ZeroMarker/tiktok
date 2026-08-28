// api.js — 轻量 fetch 封装：JSON、超时、错误提取。
export async function api(url, opt = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 12000);
  const request = {
    ...opt,
    headers: { ...(opt.headers || {}), "Content-Type": "application/json" },
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
    clearTimeout(timeout);
  }
}
