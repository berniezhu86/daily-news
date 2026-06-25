// 臻宝每日简讯 - Service Worker
// 用于PWA离线缓存和推送通知

const CACHE_NAME = 'zhenbao-news-v1.0.0';
const urlsToCache = [
  '/',
  '/index.html',
  '/images/logo.jpg'
];

// Install
self.addEventListener('install', function(event) {
  event.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(urlsToCache);
    })
  );
});

// Activate - clean old caches
self.addEventListener('activate', function(event) {
  event.waitUntil(
    caches.keys().then(function(cacheNames) {
      return Promise.all(
        cacheNames.filter(function(name) {
          return name !== CACHE_NAME;
        }).map(function(name) {
          return caches.delete(name);
        })
      );
    })
  );
});

// Fetch - network first, fallback to cache
self.addEventListener('fetch', function(event) {
  event.respondWith(
    fetch(event.request).catch(function() {
      return caches.match(event.request);
    })
  );
});

// Push notification
self.addEventListener('push', function(event) {
  let data = { title: '臻宝每日简讯', body: '每日简讯已更新，点击查看最新内容。' };
  if (event.data) {
    try { data = event.data.json(); } catch(e) { data.body = event.data.text(); }
  }
  const options = {
    body: data.body,
    icon: '/images/logo.jpg',
    badge: '/images/logo.jpg',
    vibrate: [200, 100, 200],
    requireInteraction: true,
    tag: 'zhenbao-daily',
    renotify: true,
    actions: [
      { action: 'open', title: '立即查看' },
      { action: 'close', title: '知道了' }
    ]
  };
  event.waitUntil(self.registration.showNotification(data.title, options));
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  if (event.action === 'open' || !event.action) {
    event.waitUntil(
      clients.matchAll({ type: 'window' }).then(function(clientList) {
        for (var client of clientList) {
          if (client.url && 'focus' in client) {
            return client.focus();
          }
        }
        if (clients.openWindow) {
          return clients.openWindow('/');
        }
      })
    );
  }
});
