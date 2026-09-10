/* RentaGO phone-prefix component.
 *
 * For every .phone-field group the form keeps three visible parts:
 *   - a country <select>   (class .phone-country)
 *   - a city <select>      (class .phone-city)
 *   - a local number <input> (class .phone-number)
 * plus a hidden <input> (class .phone-value) that receives the assembled
 * international number "+<cc>-<std>-<local>" on submit / change.
 *
 * The country dropdown is seeded once on first use. Default = India +91.
 */
(function () {
  "use strict";

  // country code -> display name
  var COUNTRIES = {
    IN: { name: "India", cc: "91" },
    US: { name: "United States", cc: "1" },
    GB: { name: "United Kingdom", cc: "44" },
    AE: { name: "UAE", cc: "971" },
    SG: { name: "Singapore", cc: "65" },
    SA: { name: "Saudi Arabia", cc: "966" },
    QA: { name: "Qatar", cc: "974" },
    KW: { name: "Kuwait", cc: "965" },
    OM: { name: "Oman", cc: "968" },
    LK: { name: "Sri Lanka", cc: "94" },
    BD: { name: "Bangladesh", cc: "880" },
    NP: { name: "Nepal", cc: "977" }
  };

  // country -> [ {name, area} ] ; area may be "" for "no city / nationwide"
  var CITIES = {
    IN: [
      { name: "Mumbai", area: "22" },
      { name: "Delhi NCR", area: "11" },
      { name: "Bengaluru", area: "80" },
      { name: "Hyderabad", area: "40" },
      { name: "Chennai", area: "44" },
      { name: "Kolkata", area: "33" },
      { name: "Pune", area: "20" },
      { name: "Ahmedabad", area: "79" },
      { name: "Jaipur", area: "141" },
      { name: "Lucknow", area: "522" },
      { name: "Chandigarh", area: "172" },
      { name: "Indore", area: "731" },
      { name: "Surat", area: "261" },
      { name: "Kochi", area: "484" },
      { name: "Goa", area: "832" },
      { name: "Other city", area: "" }
    ],
    US: [
      { name: "New York", area: "212" },
      { name: "Los Angeles", area: "213" },
      { name: "Chicago", area: "312" },
      { name: "Houston", area: "713" },
      { name: "San Francisco", area: "415" },
      { name: "Seattle", area: "206" },
      { name: "Boston", area: "617" },
      { name: "Other city", area: "" }
    ],
    GB: [
      { name: "London", area: "20" },
      { name: "Manchester", area: "161" },
      { name: "Birmingham", area: "121" },
      { name: "Leeds", area: "113" },
      { name: "Glasgow", area: "141" },
      { name: "Other city", area: "" }
    ],
    AE: [
      { name: "Dubai", area: "4" },
      { name: "Abu Dhabi", area: "2" },
      { name: "Sharjah", area: "6" },
      { name: "Other city", area: "" }
    ],
    SG: [{ name: "Singapore", area: "" }],
    SA: [
      { name: "Riyadh", area: "11" },
      { name: "Jeddah", area: "12" },
      { name: "Dammam", area: "13" },
      { name: "Other city", area: "" }
    ],
    QA: [{ name: "Doha", area: "" }],
    KW: [{ name: "Kuwait City", area: "" }],
    OM: [{ name: "Muscat", area: "" }],
    LK: [{ name: "Colombo", area: "11" }, { name: "Other city", area: "" }],
    BD: [{ name: "Dhaka", area: "2" }, { name: "Other city", area: "" }],
    NP: [{ name: "Kathmandu", area: "1" }, { name: "Other city", area: "" }]
  };

  function seedCountries() {
    if (document.querySelector("[data-phone-seeded]")) return;
    document.querySelectorAll(".phone-field").forEach(function (group) {
      group.setAttribute("data-phone-seeded", "1");
      var countrySel = group.querySelector(".phone-country");
      Object.keys(COUNTRIES).forEach(function (code) {
        var opt = document.createElement("option");
        opt.value = code;
        opt.textContent = COUNTRIES[code].name + " (+" + COUNTRIES[code].cc + ")";
        countrySel.appendChild(opt);
      });
      countrySel.value = group.getAttribute("data-default-country") || "IN";
      rebuildCities(group);
      assemble(group);
    });
    // Bind on the wrapper so dynamically added fields also work.
    document.addEventListener("change", function (e) {
      var group = e.target && e.target.closest ? e.target.closest(".phone-field") : null;
      if (!group) return;
      if (e.target.classList.contains("phone-country")) {
        rebuildCities(group);
      }
      assemble(group);
    });
    document.addEventListener("input", function (e) {
      var group = e.target && e.target.closest ? e.target.closest(".phone-field") : null;
      if (group && e.target.classList.contains("phone-number")) assemble(group);
    });
    // Assemble the hidden value on any submit so it is always fresh.
    document.addEventListener("submit", function (e) {
      e.target.querySelectorAll(".phone-field").forEach(assemble);
    }, true);
  }

  function rebuildCities(group) {
    var code = group.querySelector(".phone-country").value;
    var citySel = group.querySelector(".phone-city");
    citySel.innerHTML = "";
    (CITIES[code] || [{ name: "Other city", area: "" }]).forEach(function (c) {
      var opt = document.createElement("option");
      opt.value = c.area;
      opt.textContent = c.name + (c.area ? " (STD " + c.area + ")" : "");
      citySel.appendChild(opt);
    });
    citySel.value = normalizeArea(group.getAttribute("data-default-area"));
  }

  function normalizeArea(area) {
    if (!area || area === "?") return "";
    // accept "+91-22-", "022-", "22" as an area, map to "22"
    var m = String(area).match(/(\d{1,4})\s*$/);
    return m ? m[1] : "";
  }

  function assemble(group) {
    var cc = COUNTRIES[group.querySelector(".phone-country").value].cc;
    var area = group.querySelector(".phone-city").value || "";
    var num = String(group.querySelector(".phone-number").value || "").replace(/\D/g, "");
    var parts = ["+" + cc];
    if (area) parts.push(area);
    if (num) parts.push(num);
    group.querySelector(".phone-value").value = parts.join("-");
  }

  document.addEventListener("DOMContentLoaded", seedCountries);
  if (document.readyState !== "loading") seedCountries();
})();
