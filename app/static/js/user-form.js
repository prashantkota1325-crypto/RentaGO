/* Dependent organization -> person selection for Super Admin user management. */
(function () {
  "use strict";
  var company = document.getElementById("user_company");
  var role = document.getElementById("user_role");
  var name = document.getElementById("user_name");
  var manual = document.getElementById("user_manual_name");
  var email = document.getElementById("user_email");
  var mobile = document.querySelector('input[name="mobile"]');
  if (!company || !role || !name || !email) return;

  function isVendor() {
    return (role.value || "").toLowerCase().indexOf("vendor") === 0;
  }

  function setManual(on) {
    manual.style.display = on ? "" : "none";
    manual.required = on;
    email.readOnly = !on;
    if (!on) manual.value = "";
  }

  function loadPeople() {
    var opt = company.options[company.selectedIndex];
    var id = opt && opt.getAttribute("data-org-id");
    var kind = (opt && opt.getAttribute("data-kind")) || (isVendor() ? "vendor" : "corporate");
    name.innerHTML = '<option value="">Loading names...</option><option value="__manual__">Enter name manually</option>';
    setManual(false);
    if (id === "__new__") {
      name.innerHTML = '<option value="__manual__" selected>Enter new individual guest</option>';
      setManual(true);
      return;
    }
    if (!id) {
      name.innerHTML = '<option value="">Select a company first</option>' +
        '<option value="__manual__">Enter name manually</option>';
      return;
    }
    fetch("/auth/user-directory?company_id=" + encodeURIComponent(id) + "&kind=" + kind)
      .then(function (r) { return r.json(); })
      .then(function (items) {
        name.innerHTML = '<option value="">Select a person</option>';
        items.forEach(function (p) {
          var o = document.createElement("option");
          o.value = p.name; o.textContent = p.name + (p.email ? " - " + p.email : "");
          o.dataset.email = p.email; o.dataset.mobile = p.mobile;
          name.appendChild(o);
        });
        if (!name.querySelector('option[value="__manual__"]')) {
          var manualOpt = document.createElement("option");
          manualOpt.value = "__manual__"; manualOpt.textContent = "Enter name manually";
          name.appendChild(manualOpt);
        }
      })
      .catch(function () {
         name.innerHTML = '<option value="__manual__">Enter name manually</option>';
        name.value = "__manual__"; setManual(true);
      });
  }

  company.addEventListener("change", loadPeople);
  role.addEventListener("change", loadPeople);
  name.addEventListener("change", function () {
    var opt = name.options[name.selectedIndex];
    var manualChoice = name.value === "__manual__";
    setManual(manualChoice);
    if (!manualChoice && opt) {
      email.value = opt.dataset.email || "";
      if (mobile) mobile.value = opt.dataset.mobile || mobile.value;
    }
  });
  if (company.value) loadPeople();
})();
