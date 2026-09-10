/* RentaGO allocation pick-lists (Steps 2-3).
 *
 * Attaches autocomplete to:
 *   [data-vendor-search]  -> /bookings/vendors?q=   (fills vendor_contact + vendor_email)
 *   [data-driver-search]  -> /bookings/drivers?q=   (fills driver_contact)
 *   [data-vehicle-search] -> /bookings/vehicles?q=  (fills the input itself with reg no)
 *
 * Free text remains allowed (masters are a convenience, not a hard gate).
 */
(function () {
  "use strict";

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function attach(input, endpoint, render, pick) {
    var wrap = document.createElement("div");
    wrap.style.position = "relative";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);

    var list = document.createElement("div");
    list.className = "list-group position-absolute w-100 shadow";
    list.style.maxHeight = "260px";
    list.style.overflow = "auto";
    list.style.display = "none";
    list.style.zIndex = "1050";
    wrap.appendChild(list);

    var timer = null;
    input.addEventListener("input", function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < 2) {
        list.style.display = "none";
        list.innerHTML = "";
        return;
      }
      timer = setTimeout(function () {
        fetch(endpoint + encodeURIComponent(q))
          .then(function (r) { return r.json(); })
          .then(function (items) {
            list.innerHTML = "";
            if (!items.length) {
              list.style.display = "none";
              return;
            }
            items.forEach(function (item) {
              var a = document.createElement("button");
              a.type = "button";
              a.className = "list-group-item list-group-item-action text-start";
              a.innerHTML = render(item);
              a.addEventListener("mousedown", function (e) { e.preventDefault(); });
              a.addEventListener("click", function () {
                pick(input, item);
                list.style.display = "none";
              });
              list.appendChild(a);
            });
            list.style.display = "block";
          })
          .catch(function () { list.style.display = "none"; });
      }, 250);
    });
    document.addEventListener("click", function (e) {
      if (!wrap.contains(e.target)) { list.style.display = "none"; }
    });
  }

  function fill(form, name, value) {
    if (!form || !value) return;
    var el = form.querySelector("[name=" + name + "]");
    if (el) el.value = value;
  }

  function init() {
    document.querySelectorAll("[data-vendor-search]").forEach(function (input) {
      if (input.dataset.init) return;
      input.dataset.init = "1";
      attach(input, "/bookings/vendors?q=", function (v) {
        return "<b>" + escapeHtml(v.name) + "</b>" +
          (v.contact ? " &mdash; " + escapeHtml(v.contact) : "") +
          (v.email ? " <span class='text-muted'>" + escapeHtml(v.email) + "</span>" : "");
      }, function (input, v) {
        var form = input.closest("form");
        input.value = v.name;
        fill(form, "vendor_contact", v.contact);
        fill(form, "vendor_email", v.email);
      });
    });

    document.querySelectorAll("[data-driver-search]").forEach(function (input) {
      if (input.dataset.init) return;
      input.dataset.init = "1";
      attach(input, "/bookings/drivers?q=", function (d) {
        return "<b>" + escapeHtml(d.name) + "</b>" +
          (d.contact ? " &mdash; " + escapeHtml(d.contact) : "");
      }, function (input, d) {
        var form = input.closest("form");
        input.value = d.name;
        fill(form, "driver_contact", d.contact);
      });
    });

    document.querySelectorAll("[data-vehicle-search]").forEach(function (input) {
      if (input.dataset.init) return;
      input.dataset.init = "1";
      attach(input, "/bookings/vehicles?q=", function (v) {
        return "<b>" + escapeHtml(v.reg) + "</b>" +
          (v.category ? " <span class='text-muted'>" + escapeHtml(v.category) + "</span>" : "");
      }, function (input, v) {
        input.value = v.reg;
      });
    });
  }

  document.addEventListener("DOMContentLoaded", init);
  if (document.readyState !== "loading") init();
})();
