// ===== SHIELDAI SERVICE WORKER =====
// Bump CACHE_VERSION whenever you update app files to force cache refresh.
const CACHE_VERSION = 'v3';
const STATIC_CACHE  = `shieldai-static-${CACHE_VERSION}`;
const OFFLINE_QUEUE_KEY = 'sw_offline_scan_queue';

// Core app shell assets — only same-origin static files (NOT cross-origin API)
const STATIC_ASSETS = [
  './',
  './index.html',
  './style.css',
  './app.js',
  './manifest.json',
  './icons/icon-192.png',
  './icons/icon-512.png',
];

// ===== INSTALL — cache assets individually so one failure doesn't break all =====
self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(STATIC_CACHE).then(async cache => {
      const results = await Promise.allSettled(
        STATIC_ASSETS.map(url => cache.add(url).catch(err => {
          console.warn(`[SW] Failed to cache: ${url}`, err);
        }))
      );
      const failed = results.filter(r => r.status === 'rejected');
      if (failed.length) console.warn(`[SW] ${failed.length} asset(s) not cached.`);
      console.log('[SW] Install complete.');
    })
  );
  // Activate immediately — don't wait for old tabs to close
  self.skipWaiting();
});

// ===== ACTIVATE — purge stale caches =====
self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(k => k.startsWith('shieldai-') && k !== STATIC_CACHE)
          .map(k => {
            console.log('[SW] Deleting old cache:', k);
            return caches.delete(k);
          })
      )
    ).then(() => {
      console.log('[SW] Activated, controlling all clients.');
      return self.clients.claim();
    })
  );
});

// ===== FETCH — Cache-first for static assets only =====
// NOTE: API calls go to a different origin (e.g. 10.195.110.169:8000).
// Service workers can only intercept same-origin requests by default.
// API requests are handled entirely in app.js with fetch() + offline queue.
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Only handle GET requests for same-origin static assets
  if (e.request.method !== 'GET') return;
  if (url.origin !== self.location.origin) return; // Skip cross-origin (API, fonts CDN)

  // Skip Chrome extension URLs
  if (url.protocol === 'chrome-extension:') return;

  e.respondWith(
    caches.match(e.request).then(cached => {
      if (cached) {
        // Serve from cache, then update in background (stale-while-revalidate)
        const networkFetch = fetch(e.request).then(res => {
          if (res && res.status === 200) {
            const clone = res.clone();
            caches.open(STATIC_CACHE).then(c => c.put(e.request, clone));
          }
          return res;
        }).catch(() => {});
        return cached; // return cached immediately
      }
      // Not in cache — fetch from network
      return fetch(e.request).then(res => {
        if (!res || res.status !== 200) return res;
        const clone = res.clone();
        caches.open(STATIC_CACHE).then(c => c.put(e.request, clone));
        return res;
      }).catch(() => {
        // Return offline fallback for navigation requests
        if (e.request.mode === 'navigate') {
          return caches.match('./index.html');
        }
      });
    })
  );
});

// ===== MESSAGE — receive commands from app.js =====
self.addEventListener('message', e => {
  if (e.data?.type === 'SKIP_WAITING') self.skipWaiting();
  if (e.data?.type === 'GET_VERSION')  e.ports[0].postMessage({ version: CACHE_VERSION });
});
