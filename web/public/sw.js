// Safe network-first service worker for AMARKAL Platform PWA installability.
// Strictly bypasses /v1/ API and /auth-config.json to guarantee zero stale or cross-tenant caching.
const CACHE_NAME = "amarkal-shell-v2";

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (
    url.origin !== self.location.origin ||
    url.pathname.startsWith("/v1/") ||
    url.pathname === "/auth-config.json" ||
    url.pathname.startsWith("/auth/")
  ) {
    return;
  }
  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok && url.pathname.startsWith("/_next/static/")) {
          const clone = res.clone();
          void caches.open(CACHE_NAME).then((cache) => cache.put(req, clone));
        }
        return res;
      })
      .catch(() => caches.match(req)),
  );
});
