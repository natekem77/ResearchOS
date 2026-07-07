const RESEARCHOS_CACHE = "researchos-pwa-v1";
const STATIC_ASSETS = [
  "/",
  "/frontend-assets/styles.css",
  "/frontend-assets/app.js",
  "/frontend-assets/manifest.webmanifest",
  "/frontend-assets/icons/icon.svg",
  "/frontend-assets/icons/maskable-icon.svg"
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(RESEARCHOS_CACHE).then((cache) => cache.addAll(STATIC_ASSETS)).catch(() => undefined)
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== RESEARCHOS_CACHE).map((key) => caches.delete(key)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  const isStatic = url.pathname === "/" || url.pathname.startsWith("/frontend-assets/");
  if (!isStatic) return;

  event.respondWith(
    caches.match(request).then((cached) =>
      cached || fetch(request).then((response) => {
        const copy = response.clone();
        caches.open(RESEARCHOS_CACHE).then((cache) => cache.put(request, copy));
        return response;
      })
    )
  );
});
