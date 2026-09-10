/* RentaGO minimal service worker.
 *
 * The app is fully online (Oracle DB on the host PC), so no offline caching is
 * done - this worker exists only so browsers treat the link as an installable
 * app (Add to Home Screen / Install app) with the RentaGO name and logo.
 * Every request passes straight through to the network.
 */
self.addEventListener("install", function (e) {
  self.skipWaiting();
});

self.addEventListener("activate", function (e) {
  self.clients.claim();
});

self.addEventListener("fetch", function (e) {
  /* network passthrough - nothing to intercept */
});
