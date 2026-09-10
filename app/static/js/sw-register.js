/* Register the RentaGO service worker (installable app icon).
 * Only possible over HTTPS (the public tunnel link) - silently skipped on
 * plain LAN http, where the favicon + manifest still brand the site. */
if ("serviceWorker" in navigator && location.protocol === "https:") {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {});
  });
}
