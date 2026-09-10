/* RentaGO unified guest search.
 *
 * Turns any input marked [data-guest-search] into an autocomplete that queries
 * the merged Employees + Individuals endpoint (/bookings/guests?q=). On pick it
 * fills the guest name, email (if present) and the phone-field's number input.
 */
(function () {
  "use strict";

  function init() {
    document.querySelectorAll("[data-guest-search]").forEach(function (input) {
      if (input.dataset.init) return;
      input.dataset.init = "1";
      build(input);
    });
  }

  function build(input) {
    // container to position the dropdown under the input
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
      timer = setTimeout(function () { fetchGuests(input, list, q); }, 250);
    });
    document.addEventListener("click", function (e) {
      if (!wrap.contains(e.target)) { list.style.display = "none"; }
    });
  }

  function fetchGuests(input, list, q) {
    fetch("/bookings/guests?q=" + encodeURIComponent(q))
      .then(function (r) { return r.json(); })
      .then(function (items) {
        list.innerHTML = "";
        if (!items.length) {
          list.style.display = "none";
          return;
        }
        items.forEach(function (g) {
          var a = document.createElement("button");
          a.type = "button";
          a.className = "list-group-item list-group-item-action text-start";
          a.innerHTML = "<b>" + escapeHtml(g.guest_name) + "</b>" +
            (g.company ? " &mdash; " + escapeHtml(g.company) : "") +
            (g.code ? " <span class='text-muted'>(" + escapeHtml(g.code) + ")</span>" : "") +
            "<span class='badge bg-light text-dark float-end'>" + g.source + "</span>";
          a.addEventListener("mousedown", function (e) { e.preventDefault(); });
          a.addEventListener("click", function () { pick(input, g); list.style.display = "none"; });
          list.appendChild(a);
        });
        list.style.display = "block";
      })
      .catch(function () { list.style.display = "none"; });
  }

  function pick(input, g) {
    input.value = g.guest_name;
    var form = input.closest("form");
    if (form) {
      // ---- auto-reflect all related fields (company / entity / ids / admin) ----
      set(form, "company_name", g.company);
      set(form, "entity_name", g.entity);
      set(form, "company_id", g.company_id);
      set(form, "emp_guest_id", g.code);
      set(form, "guest_email", g.email);
      set(form, "admin_name", g.admin_name);
      set(form, "admin_email", g.admin_email);
      fillPhone(form, "guest_contact", g.mobile);
      fillPhone(form, "admin_contact", g.admin_mobile);
    }
  }

  function set(form, name, value) {
    var el = form && form.querySelector('[name="' + name + '"]');
    if (el && value) el.value = value;
  }

  function fillPhone(form, name, raw) {
    // phone fields render visible country/city/number controls plus a hidden
    // <input name=...> that carries the assembled value - fill the number box
    // and let phone-prefix.js reassemble the hidden value.
    var hidden = form && form.querySelector('input[name="' + name + '"]');
    if (!hidden) return;
    var box = hidden.closest(".phone-field");
    if (!box) return;
    var num = box.querySelector(".phone-number");
    var digits = String(raw || "").replace(/\D/g, "");
    if (num && digits) {
      num.value = digits.replace(/^91(?=\d{10}$)/, ""); // strip India cc if present
      var ev = new Event("input", { bubbles: true });
      num.dispatchEvent(ev);
    }
  }

  function escapeHtml(s) {
    return String(s || "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  document.addEventListener("DOMContentLoaded", init);
  if (document.readyState !== "loading") init();
})();
