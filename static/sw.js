// Cachea el shell para que la app abra offline. Las búsquedas NO se cachean
// (dependen del server); si no hay red, se muestra el mensaje de error del front.
const CACHE = "comparador-v1";
const SHELL = [
  "/",
  "/static/index.html",
  "/static/manifest.json",
  "/static/icon.svg",
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  // Network-first para /api/*, cache-first para el shell.
  if (url.pathname.startsWith("/api/")) {
    e.respondWith(fetch(e.request).catch(() => new Response(
      JSON.stringify({ error: "Sin conexión. Probá de nuevo cuando vuelva la red." }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    )));
    return;
  }
  e.respondWith(
    caches.match(e.request).then((hit) => hit || fetch(e.request).then((res) => {
      if (res.ok && url.origin === location.origin) {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, copy));
      }
      return res;
    }))
  );
});