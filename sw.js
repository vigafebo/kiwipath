const CACHE_NAME = "kiwipath-pwa-v4";
const APP_BASE = "/kiwipath/";
const APP_SHELL = [APP_BASE, APP_BASE + "manifest.webmanifest"];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(APP_SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(key => key.startsWith("kiwipath-") && key !== CACHE_NAME).map(key => caches.delete(key)))).then(() => self.clients.claim()));
});

// Network-first for the app shell; fall back to the cached shell if offline.
self.addEventListener("fetch", event => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin || !url.pathname.startsWith(APP_BASE)) return;
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).then(response => {
      if (response.ok) caches.open(CACHE_NAME).then(cache => cache.put(APP_BASE, response.clone()));
      return response;
    }).catch(() => caches.match(APP_BASE)));
  }
});

// Push listener is included now; the server-side sender will be connected in the next phase.
self.addEventListener("push", event => {
  let payload = {};
  try { payload = event.data ? event.data.json() : {}; }
  catch (_) { payload = { body: event.data ? event.data.text() : "Abra o KiwiPath para conferir as novidades." }; }
  const title = payload.title || "KiwiPath";
  const options = {
    body: payload.body || "Você tem uma atualização no KiwiPath.",
    icon: "/kiwipath/icons/kiwipath-192.png",
    badge: "/kiwipath/icons/kiwipath-192.png",
    tag: payload.tag || "kiwipath-update",
    data: { url: payload.url || "/kiwipath/" },
    renotify: false
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", event => {
  event.notification.close();
  const target = new URL(event.notification.data?.url || "/kiwipath/", self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(clients => {
    for (const client of clients) {
      if (client.url.startsWith(self.location.origin + "/kiwipath/") && "focus" in client) return client.focus();
    }
    return self.clients.openWindow(target);
  }));
});
