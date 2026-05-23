const CACHE_NAME    = 'telugu-kathalu-v8';
const RUNTIME_CACHE = 'telugu-kathalu-runtime-v8';

const PRECACHE_ASSETS = [
  '/static/style.css',
  '/static/hero-bg.webp',
  '/static/icon-192.png',
  '/static/icon-512.png',
];

// ── INSTALL ──────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// ── ACTIVATE: clean up old caches ────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k !== CACHE_NAME && k !== RUNTIME_CACHE)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ── FETCH ────────────────────────────────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== location.origin) return;

  // Never intercept HTML page navigations — let the browser fetch them directly.
  // This prevents ERR_FAILED on page links and keeps HTML always fresh.
  if (request.mode === 'navigate') return;

  const path = url.pathname;

  // JSON — stale-while-revalidate: serve cached version immediately so the
  // page renders without waiting for the network, then update cache in background.
  if (path.endsWith('.json')) {
    event.respondWith(staleWhileRevalidate(request));
    return;
  }

  // Audio — cache-first (large files, rarely change)
  if (path.endsWith('.mp3')) {
    event.respondWith(cacheFirst(request, RUNTIME_CACHE));
    return;
  }

  // Images — cache-first
  if (path.match(/\.(jpg|jpeg|png|webp|svg)$/i)) {
    event.respondWith(cacheFirst(request, RUNTIME_CACHE));
    return;
  }

  // CSS / JS / icons — cache-first (precached on install)
  event.respondWith(cacheFirst(request, CACHE_NAME));
});

// ── STRATEGIES ───────────────────────────────────────────────────────────────
// Serve from cache immediately (instant render), then fetch fresh copy in
// background and update cache for next visit. Falls back to network on first load.
async function staleWhileRevalidate(request) {
  const cached = await caches.match(request);
  const fetchPromise = fetch(request).then(response => {
    if (response.ok) {
      caches.open(RUNTIME_CACHE).then(cache => cache.put(request, response.clone()));
    }
    return response;
  }).catch(() => null);
  return cached || await fetchPromise || new Response('{}', {
    headers: { 'Content-Type': 'application/json' }
  });
}

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch (_) {
    return new Response('Not found', { status: 404 });
  }
}
