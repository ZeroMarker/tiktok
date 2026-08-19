/* Live Stream WebUI - service worker
 * Strategy:
 *  - API requests: never intercepted (auth headers / live data stay network-only)
 *  - Navigation: network-first, falls back to the cached app shell when offline
 *  - Static assets (manifest/icons): stale-while-revalidate
 * All paths are relative to the SW script, so it works both directly
 * (127.0.0.1:8766/) and behind Caddy's /tiktok/ path stripping.
 */
const CACHE = "livestream-webui-v2";
const ASSETS = [
  "./",
  "./manifest.webmanifest",
  "./icon-32.png",
  "./icon-180.png",
  "./icon-192.png",
  "./icon-512.png",
  "./icon-maskable-512.png",
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
  if (url.origin !== self.location.origin) return;
  // Never touch the API: it carries auth data and must always be live.
  if (url.pathname.includes("/api/")) return;

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