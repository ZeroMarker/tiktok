// api.js — 后端接口（同源 /api/*）。错误统一抛 Error(后端的 error 文案)。
async function parse(r) {
  const raw = await r.text();
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    throw new Error(`服务器返回非 JSON（HTTP ${r.status}）：${raw.slice(0, 240)}`);
  }
  if (!r.ok) throw new Error(data.error || r.statusText || String(r.status));
  return data;
}

export async function get(path) {
  return parse(await fetch(path, { cache: "no-store" }));
}

export async function post(path, data = {}) {
  return parse(await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  }));
}

export async function uploadCover(file) {
  const form = new FormData();
  form.append("file", file);
  return parse(await fetch("/api/cover", { method: "POST", body: form, cache: "no-store" }));
}

export const fetchStatus = () => get("/api/status");
export const fetchLogs = (which, tail) =>
  get(`/api/logs?which=${encodeURIComponent(which)}&tail=${encodeURIComponent(tail)}`);
