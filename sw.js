const CACHE_NAME    = 'telugu-kathalu-v1';
const RUNTIME_CACHE = 'telugu-kathalu-runtime-v1';

// Assets that are always cached on install
const PRECACHE_ASSETS = [
  '/',
  '/index.html',
  '/story.html',
  '/favorites.html',
  '/static/style.css',
  '/static/icon-192.png',
  '/static/icon-512.png',
  '/manifest.json',
];

// ── INSTALL: precache shell assets ──────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// ── ACTIVATE: clean up old caches ───────────────────────────────────────────
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

// ── FETCH: strategy by resource type ────────────────────────────────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Only handle same-origin requests
  if (url.origin !== location.origin) return;

  const path = url.pathname;

  // JSON files (index.json, story.json, categories.json) — network-first
  if (path.endsWith('.json')) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Audio files — cache-first (large, rarely change)
  if (path.endsWith('.mp3')) {
    event.respondWith(cacheFirst(request, RUNTIME_CACHE));
    return;
  }

  // Images — cache-first
  if (path.match(/\.(jpg|jpeg|png|webp|svg)$/i)) {
    event.respondWith(cacheFirst(request, RUNTIME_CACHE));
    return;
  }

  // HTML + CSS + JS shell — cache-first (precached on install)
  event.respondWith(cacheFirst(request, CACHE_NAME));
});

// ── STRATEGIES ────────────────────────────────────────────────────────────────
async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(RUNTIME_CACHE);
      cache.put(request, response.clone());
    }
    return response;
  } catch (_) {
    const cached = await caches.match(request);
    return cached || new Response('{}', {
      headers: { 'Content-Type': 'application/json' }
    });
  }
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
