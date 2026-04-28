const CACHE_NAME = "sativus-shell-v2"; // Bumped to clear old v1 cache
const CORE_ASSETS = ["/", "/manifest.json"];

// API routes that should NEVER be cached
const API_ROUTES = ["/analyze", "/voice", "/metrics"];

self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(CORE_ASSETS)).then(() => self.skipWaiting())
    );
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
        ).then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const { request } = event;

    // 1. Never intercept or cache API routes
    if (API_ROUTES.some(route => request.url.includes(route))) {
        return;
    }

    // 2. Only handle GET requests for caching
    if (request.method !== "GET") return;

    event.respondWith(
        caches.match(request).then((cached) => {
            // Return cached version if available
            if (cached) return cached;

            // Otherwise fetch from network
            return fetch(request)
                .then((response) => {
                    // Only cache valid, successful responses (avoids caching opaque errors)
                    if (response.status === 200) {
                        const resClone = response.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(request, resClone));
                    }
                    return response;
                })
                .catch(() => {
                    // 3. If offline and fetching a page, fallback to the app shell.
                    // This prevents returning HTML for broken images/scripts.
                    if (request.mode === 'navigate') {
                        return caches.match("/");
                    }
                    // For everything else (images, fonts), just fail silently
                    return Response.error();
                });
        })
    );
});