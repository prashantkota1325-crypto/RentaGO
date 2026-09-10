/* RentaGO time dropdowns.
 *
 * Every .time-dd <select> is paired with a hidden input that carries the
 * real server-side field name. Picking an option syncs the hidden value;
 * picking "Other (type time)" reveals a free-text box for arbitrary times
 * (e.g. 10:35 or 02:15 PM). Existing values that don't match a 15-minute
 * option automatically select "Other" and show the stored value.
 */
(function () {
  "use strict";

  function init() {
    document.querySelectorAll("select.time-dd").forEach(function (sel) {
      if (sel.dataset.tdd) return;
      sel.dataset.tdd = "1";
      var box = sel.parentNode;
      var hidden = box.querySelector('input[type=hidden]');
      var other = box.querySelector("input.time-other");
      if (!hidden) return;

      // preselect: match an option, else fall back to Other with the raw value
      var initial = String(hidden.value || "").trim();
      var has = Array.prototype.some.call(sel.options, function (o) {
        return o.value && o.value !== "__other__" && o.value === initial;
      });
      if (has) {
        sel.value = initial;
      } else if (initial) {
        sel.value = "__other__";
        if (other) { other.style.display = ""; other.value = initial; }
      }

      function sync() {
        if (sel.value === "__other__") {
          if (other) other.style.display = "";
          hidden.value = other ? other.value : "";
        } else {
          if (other) other.style.display = "none";
          hidden.value = sel.value;
        }
      }

      sel.addEventListener("change", sync);
      if (other) {
        other.addEventListener("input", function () {
          if (sel.value === "__other__") hidden.value = other.value;
        });
      }
      var form = sel.closest("form");
      if (form) form.addEventListener("submit", sync);
      sync();
    });
  }

  document.addEventListener("DOMContentLoaded", init);
  if (document.readyState !== "loading") init();
})();
