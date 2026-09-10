/* RentaGO booking form enhancements (Step 1 wizard).
 *
 * 1. Company autocomplete: [data-company-search] queries /bookings/companies
 *    and on pick fills Company Name, hidden Company Id and Entity Name
 *    (the company's legal name).
 * 2. City -> State: when a known city is typed in the pickup/drop city field,
 *    the State dropdown auto-selects the matching state.
 * 3. GPS map search: the Pickup/Drop "Search GPS" button builds a query in the
 *    sequence Location Address, City, State, Country and calls
 *    /bookings/geocode (OpenStreetMap). Picking a result fills the address,
 *    stores "lat, lon" in the hidden gps field and shows a maps link.
 * 4. Package Type: selecting "Other" reveals a free-text box.
 */
(function () {
  "use strict";

  // ---- India states / UTs (State dropdown options) ----
  var IN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand",
    "Karnataka", "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur",
    "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan",
    "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh",
    "Uttarakhand", "West Bengal", "Andaman and Nicobar Islands",
    "Chandigarh", "Dadra and Nagar Haveli and Daman and Diu", "Delhi",
    "Jammu and Kashmir", "Ladakh", "Lakshadweep", "Puducherry",
  ];

  // ---- City -> State map (auto-select state when the city is known) ----
  var CITY_STATE = {
    "mumbai": "Maharashtra", "pune": "Maharashtra", "nagpur": "Maharashtra",
    "nashik": "Maharashtra", "thane": "Maharashtra", "aurangabad": "Maharashtra",
    "kolhapur": "Maharashtra", "solapur": "Maharashtra", "amravati": "Maharashtra",
    "ahmednagar": "Maharashtra", "vapi": "Gujarat", "surat": "Gujarat",
    "vadodara": "Gujarat", "rajkot": "Gujarat", "gandhinagar": "Gujarat",
    "ahmedabad": "Gujarat", "bharuch": "Gujarat", "ankleshwar": "Gujarat",
    "delhi": "Delhi", "new delhi": "Delhi", "noida": "Uttar Pradesh",
    "greater noida": "Uttar Pradesh", "ghaziabad": "Uttar Pradesh",
    "gurgaon": "Haryana", "gurugram": "Haryana", "faridabad": "Haryana",
    "bangalore": "Karnataka", "bengaluru": "Karnataka", "mysore": "Karnataka",
    "mysuru": "Karnataka", "hubli": "Karnataka", "mangalore": "Karnataka",
    "chennai": "Tamil Nadu", "coimbatore": "Tamil Nadu", "madurai": "Tamil Nadu",
    "trichy": "Tamil Nadu", "tiruchirappalli": "Tamil Nadu", "salem": "Tamil Nadu",
    "hyderabad": "Telangana", "secunderabad": "Telangana", "warangal": "Telangana",
    "kolkata": "West Bengal", "howrah": "West Bengal", "durgapur": "West Bengal",
    "jaipur": "Rajasthan", "udaipur": "Rajasthan", "jodhpur": "Rajasthan",
    "lucknow": "Uttar Pradesh", "kanpur": "Uttar Pradesh", "varanasi": "Uttar Pradesh",
    "agra": "Uttar Pradesh", "prayagraj": "Uttar Pradesh", "allahabad": "Uttar Pradesh",
    "chandigarh": "Chandigarh", "mohali": "Punjab", "ludhiana": "Punjab",
    "amritsar": "Punjab", "bhopal": "Madhya Pradesh", "indore": "Madhya Pradesh",
    "gwalior": "Madhya Pradesh", "jabalpur": "Madhya Pradesh",
    "patna": "Bihar", "ranchi": "Jharkhand", "jamshedpur": "Jharkhand",
    "bhubaneswar": "Odisha", "cuttack": "Odisha", "visakhapatnam": "Andhra Pradesh",
    "vijayawada": "Andhra Pradesh", "guntur": "Andhra Pradesh",
    "guwahati": "Assam", "silchar": "Assam", "shillong": "Meghalaya",
    "imphal": "Manipur", "kohima": "Nagaland", "aizawl": "Mizoram",
    "agartala": "Tripura", "dehradun": "Uttarakhand", "haridwar": "Uttarakhand",
    "srinagar": "Jammu and Kashmir", "jammu": "Jammu and Kashmir",
    "leh": "Ladakh", "port blair": "Andaman and Nicobar Islands",
    "panaji": "Goa", "panjim": "Goa", "puducherry": "Puducherry",
    "pondicherry": "Puducherry", "kochi": "Kerala", "cochin": "Kerala",
    "thiruvananthapuram": "Kerala", "trivandrum": "Kerala", "kozhikode": "Kerala",
    "calicut": "Kerala",
  };

  function stateSelect(name) {
    var el = document.querySelector('select[name="' + name + '"]');
    return el;
  }

  function fillStates() {
    ["pickup_state", "drop_state"].forEach(function (n) {
      var sel = stateSelect(n);
      if (!sel || sel.dataset.filled) return;
      sel.dataset.filled = "1";
      var keep = sel.getAttribute("data-value") || sel.value;
      sel.innerHTML = '<option value=""></option>' +
        IN_STATES.map(function (s) { return '<option value="' + s + '">' + s + "</option>"; }).join("") +
        '<option value="Other">Other</option>';
      if (keep) sel.value = keep;
    });
  }

  function wireCityState(cityName, stateName) {
    var city = document.querySelector('input[name="' + cityName + '"]');
    var sel = stateSelect(stateName);
    if (!city || !sel) return;
    function apply() {
      var st = CITY_STATE[city.value.trim().toLowerCase()];
      if (st) sel.value = st;
      else if (!city.value.trim()) sel.value = "";
    }
    city.addEventListener("input", apply);
    city.addEventListener("change", apply);
  }

  // ---- company autocomplete ----
  function wireCompanySearch() {
    var input = document.querySelector("[data-company-search]");
    if (!input) return;
    var wrap = document.createElement("div");
    wrap.style.position = "relative";
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    var list = document.createElement("div");
    list.className = "list-group position-absolute w-100 shadow";
    list.style.maxHeight = "240px";
    list.style.overflow = "auto";
    list.style.display = "none";
    list.style.zIndex = "1050";
    wrap.appendChild(list);
    var timer = null;
    input.addEventListener("input", function () {
      clearTimeout(timer);
      var q = input.value.trim();
      if (q.length < 2) { list.style.display = "none"; list.innerHTML = ""; return; }
      timer = setTimeout(function () {
        fetch("/bookings/companies?q=" + encodeURIComponent(q))
          .then(function (r) { return r.json(); })
          .then(function (items) {
            list.innerHTML = "";
            if (!items.length) { list.style.display = "none"; return; }
            items.forEach(function (c) {
              var a = document.createElement("button");
              a.type = "button";
              a.className = "list-group-item list-group-item-action text-start";
              a.innerHTML = "<b>" + esc(c.company_name) + "</b>" +
                " <span class='text-muted'>(" + esc(c.company_id) + ")</span>" +
                (c.entity ? " &mdash; " + esc(c.entity) : "");
              a.addEventListener("mousedown", function (e) { e.preventDefault(); });
              a.addEventListener("click", function () {
                var form = input.closest("form");
                if (form) {
                   setv(form, "company_name", c.company_name);
                   setv(form, "company_id", c.company_id);
                    if (c.entity) {
                      var entitySelect = form.querySelector('[name="entity_name"]');
                      if (entitySelect && entitySelect.tagName.toLowerCase() === "select") {
                        entitySelect.innerHTML = '<option value="' + esc(c.entity) + '" selected>' + esc(c.entity) + '</option>';
                      } else {
                        setv(form, "entity_name", c.entity);
                      }
                    }
                    loadCompanyEntities(form, c.company_id, c.entity);
                  if (c.city) {
                    setv(form, "pickup_city", c.city);
                    var ev = new Event("input", { bubbles: true });
                    var pc = form.querySelector('input[name="pickup_city"]');
                    if (pc) pc.dispatchEvent(ev);
                  }
                }
                input.value = c.company_name;
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
      if (!wrap.contains(e.target)) list.style.display = "none";
    });
  }

  function loadCompanyEntities(form, companyId, legacyEntity) {
    var select = form && form.querySelector('[name="entity_name"]');
    if (!select || !companyId) return;
    fetch("/bookings/company-entities?company_id=" + encodeURIComponent(companyId)).then(function (r) { return r.json(); }).then(function (items) {
      if (select.tagName.toLowerCase() !== "select") return;
      var current = select.value;
      select.innerHTML = '<option value="">Select legal entity</option>';
      if (!items.length && legacyEntity) items = [{legal_name: legacyEntity, entity_code: 'LEGACY'}];
      items.forEach(function (e) { var o=document.createElement('option'); o.value=e.legal_name; o.textContent=e.legal_name + (e.gstin ? ' · GSTIN ' + e.gstin : ''); o.dataset.entityId=e.entity_id || ''; select.appendChild(o); });
      if (current) select.value=current;
    }).catch(function () { if (legacyEntity) { select.innerHTML = '<option value="' + esc(legacyEntity) + '" selected>' + esc(legacyEntity) + '</option>'; } });
  }

  // ---- GPS map search (Location Address -> City -> State -> Country) ----
  function wireGps(prefix) { // 'pickup' | 'drop'
    var btn = document.querySelector("[data-gps-btn=" + prefix + "]");
    if (!btn) return;
    var box = document.getElementById(prefix + "_gps_box");
    var out = document.getElementById(prefix + "_gps_results");
     var badge = document.getElementById(prefix + "_gps_badge");
     var addressInput = formField(btn, prefix + "_address");
     if (addressInput) {
       addressInput.addEventListener("input", function () {
         setv(btn.closest("form"), prefix + "_manual_address", addressInput.value);
       });
     }
    btn.addEventListener("click", function () {
      var form = btn.closest("form");
      if (!form || !out) return;
      var country = val(form, prefix + "_country") || "India";
      var state = val(form, prefix + "_state");
      var city = val(form, prefix + "_city");
       var addr = val(form, prefix + "_address");
       setv(form, prefix + "_manual_address", addr);
      var q = [addr, city, state, country].filter(Boolean).join(", ");
      if (q.replace(/India/g, "").replace(/[,\s]/g, "").length < 3) {
         out.innerHTML = '<div class="text-danger small">Enter the location address first (Location Address, City, State, Country sequence).</div>';
        return;
      }
      out.innerHTML = '<div class="text-muted small">Searching the map for: <i>' + esc(q) + "</i> ...</div>";
      fetch("/bookings/geocode?q=" + encodeURIComponent(q))
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (data.error) {
            out.innerHTML = '<div class="text-danger small">' + esc(data.error) + "</div>";
            return;
          }
          if (!data.length) {
            out.innerHTML = '<div class="text-muted small">No GPS match found - refine the address (add area / landmark / pin code).</div>';
            return;
          }
          out.innerHTML = "";
          data.forEach(function (d) {
            var a = document.createElement("button");
            a.type = "button";
            a.className = "list-group-item list-group-item-action text-start small";
            a.innerHTML = esc(d.display_name) +
              ' <span class="badge bg-success ms-1">' + d.lat + ", " + d.lon + "</span>";
            a.addEventListener("mousedown", function (e) { e.preventDefault(); });
            a.addEventListener("click", function () {
              var form2 = btn.closest("form");
              // Keep the operator's full address (including unit/building).
              // The geocoder result is the map match, not a replacement address.
               setv(form2, prefix + "_gps", d.lat + ", " + d.lon);
               var mapUrl = "https://www.google.com/maps?q=" + d.lat + "," + d.lon;
               setv(form2, prefix + "_gps_link", mapUrl);
               var mapLink = document.getElementById(prefix + "_gps_map_link");
               if (mapLink) {
                 mapLink.href = mapUrl;
                 mapLink.textContent = mapUrl;
                 mapLink.style.display = "block";
               }
              setv(form2, prefix + "_lat", d.lat);
              setv(form2, prefix + "_lon", d.lon);
              if (badge) {
                badge.href = "https://www.google.com/maps?q=" + d.lat + "," + d.lon;
                badge.textContent = "GPS: " + d.lat + ", " + d.lon;
                badge.style.display = "inline-block";
              }
               out.innerHTML = '<div class="text-success small">GPS data captured for the entered address. Map match: ' +
                 d.lat + ", " + d.lon + ' &nbsp;<a target="_blank" href="https://www.google.com/maps?q=' +
                d.lat + "," + d.lon + '">open in Google Maps</a></div>';
            });
            out.appendChild(a);
          });
        })
        .catch(function () {
          out.innerHTML = '<div class="text-danger small">Map search failed (network error).</div>';
        });
    });
    if (box) box.appendChild(out);
  }

  // ---- package type "Other" ----
  function wirePackageOther() {
    var sel = document.querySelector('select[name="package_type_sel"]');
    var other = document.getElementById("package_other_row");
    var hidden = document.querySelector('input[name="package_type"]');
    if (!sel || !other || !hidden) return;
    function sync() {
      var v = sel.value;
      if (v === "Other") {
        other.style.display = "";
        hidden.value = document.getElementById("package_type_other").value;
      } else {
        other.style.display = "none";
        hidden.value = v;
      }
    }
    sel.addEventListener("change", sync);
    var ot = document.getElementById("package_type_other");
    if (ot) ot.addEventListener("input", function () {
      if (sel.value === "Other") hidden.value = ot.value;
    });
    var form = sel.closest("form");
    if (form) form.addEventListener("submit", sync);
    sync();
  }

  function val(form, name) {
    var el = form && form.querySelector('[name="' + name + '"]');
    return el ? String(el.value || "").trim() : "";
  }

  function formField(button, name) {
    var form = button && button.closest("form");
    return form && form.querySelector('[name="' + name + '"]');
  }

  function setv(form, name, value) {
    var el = form && form.querySelector('[name="' + name + '"]');
    if (el && value !== undefined && value !== null) el.value = value;
  }

  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function wireStopGps() {
    document.querySelectorAll("[data-stop-gps]").forEach(function (button) {
      button.addEventListener("click", function () {
        var form = button.closest("form");
        var name = button.getAttribute("data-stop-gps");
        var address = val(form, name);
        var prefix = name.indexOf("pickup") === 0 ? "pickup" : "drop";
        var query = [address, val(form, prefix + "_city"), val(form, prefix + "_state"), val(form, prefix + "_country") || "India"].filter(Boolean).join(", ");
        var result = form && form.querySelector('[data-stop-result="' + name + '"]');
        if (!address) { if (result) result.textContent = "Enter an address first"; return; }
        if (result) result.textContent = "Searching...";
        fetch("/bookings/geocode?q=" + encodeURIComponent(query)).then(function (r) { return r.json(); }).then(function (data) {
          if (!data || !data.length) { if (result) result.textContent = "No GPS match"; return; }
          var picked = data[0];
          setv(form, name + "_gps", picked.lat + "," + picked.lon);
          if (result) result.textContent = "GPS: " + picked.lat + ", " + picked.lon;
        }).catch(function () { if (result) result.textContent = "GPS search failed"; });
      });
    });
  }

  function init() {
    fillStates();
    wireCityState("pickup_city", "pickup_state");
    wireCityState("drop_city", "drop_state");
    wireCompanySearch();
    wireGps("pickup");
    wireGps("drop");
    wireStopGps();
    wirePackageOther();
  }

  document.addEventListener("DOMContentLoaded", init);
  if (document.readyState !== "loading") init();
})();
