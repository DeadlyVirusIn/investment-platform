// Self-destruct service worker.
//
// Background: a previous build of this app registered a service
// worker. The current build does NOT ship one. Any browser still
// carrying the old SW intercepts fetches and serves a stale cached
// bundle, hiding new code (UX-2 Phase B was invisible to users with
// the old SW even though Vite was serving the new modules).
//
// This SW replaces any previously-registered SW at the root scope,
// clears every cache it can see, unregisters itself, and reloads
// each controlled window. Once the cycle completes the browser has
// zero SWs. The bootstrap in main.tsx then refuses to re-register
// (it only registers when getRegistrations() returns non-empty), so
// after one round the browser is clean and stays clean.

self.addEventListener('install', () => {
  // Skip "waiting" so we take over from any older SW immediately,
  // even if old client tabs are still open.
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    try {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    } catch (_) {
      // best-effort
    }
    try {
      await self.registration.unregister();
    } catch (_) {
      // best-effort
    }
    const clients = await self.clients.matchAll({
      type: 'window',
      includeUncontrolled: true,
    });
    for (const client of clients) {
      try {
        client.navigate(client.url);
      } catch (_) {
        // best-effort
      }
    }
  })());
});

// Pass-through fetch — never serve a cached response from this SW.
// The handler exists so the install criteria are satisfied across
// browsers that require a fetch listener for a "real" SW.
self.addEventListener('fetch', () => {
  // intentionally empty — let the network handle every request
});
