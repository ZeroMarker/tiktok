/* Live Stream WebUI - service worker
 * Strategy:
 *  - API requests: never intercepted (auth headers / live data stay network-only)
 *  - Navigation: network-first, falls back to the cached app shell when offline
 *  - Static assets (app modules, manifest/icons): stale-while-revalidate
 *  - lit 的 CDN（esm.sh）也缓存：联网首访后可离线打开
 * All paths are relative to the SW script, so it works both directly
 * (127.0.0.1:8766/) and behind Caddy's /tiktok/ path stripping.
 */
const CACHE = "livestream-webui-v7";

// lit 的 CDN 源（对应 index.html 里 import map 的 cdn 分支）。
const CDN_ORIGINS = ["https://esm.sh"];

const ASSETS = [
  "./",
  "./manifest.webmanifest",
  "./icon-32.png",
  "./icon-180.png",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-maskable-512.png",
  // vendor 是离线/CDN 不可达时的回落（index.html 的 import map），必须预缓存整份最小闭包。
  "./vendor/lit/index.js",
  "./vendor/lit-element/lit-element.js",
  "./vendor/lit-html/lit-html.js",
  "./vendor/lit-html/is-server.js",
  "./vendor/reactive-element/reactive-element.js",
  "./vendor/reactive-element/css-tag.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(ASSETS))
      .catch(() => {
        /* pre-cache is best-effort: a failed request must not block install */
      })
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    Promise.all([
      caches
        .keys()
        .then((keys) =>
          Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key)))
        ),
      self.clients.claim(),
    ])
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  const sameOrigin = url.origin === self.location.origin;
  const cdnAsset = CDN_ORIGINS.includes(url.origin);
  if (!sameOrigin && !cdnAsset) return;
  // Never touch the API: it carries auth data and must always be live.
  if (sameOrigin && url.pathname.includes("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(networkFirst(request));
  } else {
    event.respondWith(staleWhileRevalidate(request));
  }
});

async function networkFirst(request) {
  const cache = await caches.open(CACHE);
  try {
    const response = await fetch(request);
    if (response && response.ok && response.type === "basic") {
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await cache.match(request);
    if (cached) return cached;
    const shell = await cache.match("./");
    if (shell) return shell;
    throw new Error("offline");
  }
}

async function staleWhileRevalidate(request) {
  const cache = await caches.open(CACHE);
  const cached = await cache.match(request);
  const refresh = fetch(request)
    .then((response) => {
      if (response && response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => cached);
  return cached || (await refresh);
}
