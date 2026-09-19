/* Pulse service worker: app-shell caching + network-first API. */
const CACHE = "pulse-shell-v4";
const SHELL = ["./", "./index.html", "./manifest.json", "./icon-192.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()).catch(() => {})
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Chat credentials and conversations must never enter the offline cache.
  if (url.pathname.includes("/api/assistant") || url.pathname.includes("/api/live")) return;

  if (url.pathname.includes("/api/")) {
    // Network-first for API: fresh data when online, cached when not.
    // Only cache genuine JSON responses — never cache error/HTML pages
    // as API data (a wrong-path fetch returns the SPA/dashboard HTML).
    event.respondWith(
      fetch(request)
        .then((res) => {
          const ct = res.headers.get("content-type") || "";
          if (res.ok && ct.includes("application/json")) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(request, copy)).catch(() => {});
          }
          return res;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Navigations: network-first, fall back to cached shell (offline SPA).
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put("./index.html", copy)).catch(() => {});
          return res;
        })
        .catch(() => caches.match("./index.html"))
    );
    return;
  }

  // Static assets: cache-first, refresh in background.
  event.respondWith(
    caches.match(request).then((hit) => {
      const net = fetch(request)
        .then((res) => {
          if (res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(request, copy)).catch(() => {});
          }
          return res;
        })
        .catch(() => hit);
      return hit || net;
    })
  );
});
