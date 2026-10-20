/* Bili 推流管理 Service Worker — 无构建步骤。
 * 策略：/api/* 永远走网络；/vendor/*（版本固定的依赖）缓存优先；
 * 其余（壳页面、/frontend/* 源码）网络优先、离线回退缓存——改了前端刷新即生效。 */
const CACHE = "bili-push-v5";
const SHELL = [
  "/",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon.svg",
  "/frontend/main.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

function store(request, res) {
  if (res.ok) {
    const copy = res.clone();
    caches.open(CACHE).then((cache) => cache.put(request, copy));
  }
  return res;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  // API 与日志永远走网络：状态/推流控制不能读到过期缓存。
  if (url.pathname.startsWith("/api/")) return;
  if (url.pathname.startsWith("/vendor/")) {
    event.respondWith(caches.match(request).then((hit) => hit || fetch(request).then((res) => store(request, res))));
    return;
  }
  const key = request.mode === "navigate" ? "/" : request;
  event.respondWith(
    fetch(request)
      .then((res) => store(key, res))
      .catch(() => caches.match(key, { ignoreSearch: request.mode === "navigate" })),
  );
});
