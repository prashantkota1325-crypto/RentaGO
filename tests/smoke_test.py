"""
RentaGO Web - end-to-end smoke test against a RUNNING server.

Covers: login, home, RBAC nav, booking wizard (Steps 1-3), dual-confirmation
trip lifecycle, provisional invoice + vendor expenses + payment, cancellation
invoice, payments list, dashboards, SLA check.

Usage:
    python tests/smoke_test.py [base_url] [user_id] [password]

Defaults: http://127.0.0.1:8000. Supply a test user ID and password explicitly
(create the test user with scripts/seed_admin.py before running this test).
"""

import re
import sys
import urllib.request
import urllib.parse
import http.cookiejar

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
USER = sys.argv[2] if len(sys.argv) > 2 else ""
PASSWORD = sys.argv[3] if len(sys.argv) > 3 else ""

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(jar),
)

passed = 0
failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [ok] {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name} {extra}")


def get(path):
    return opener.open(BASE + path, timeout=60).read().decode("utf-8", "replace")


def post(path, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(BASE + path, data=body)
    return opener.open(req, timeout=60).read().decode("utf-8", "replace")


def main():
    if not USER or not PASSWORD:
        print("Usage: python tests/smoke_test.py [base_url] [test_user] [test_password]")
        sys.exit(2)
    print(f"Smoke test against {BASE} as {USER}")

    # --- auth ---
    html = post("/auth/login", {"user_id": USER, "password": PASSWORD})
    check("login lands on /home", "Welcome" in html or "Change Password" in html, html[:200])
    html = get("/home")
    check("home renders + change-password card", "Change Password" in html)
    check("nav gated by RBAC (Dashboard link for super admin)", "/dashboards" in html)

    # --- booking wizard ---
    html = post("/bookings/create", {
        "booking_type": "Dummy",
        "company_name": "Smoke Test Co",
        "guest_name": "Smoke Guest",
        "guest_email": "smoke@example.com",
        "guest_contact": "9999999999",
        "pickup_address": "Gate 1, Test Campus",
        "pickup_city": "Pune",
        "pickup_date": "31-12-2026",
        "pickup_time": "10:00 AM",
        "drop_address": "Airport Road, Test City",
        "drop_city": "Mumbai",
        "vehicle_type": "Sedan",
    })
    m = re.search(r"DM-(\d+)", html)
    check("step 1 creates DM- booking", bool(m))
    booking_id = f"DM-{m.group(1)}" if m else ""

    if booking_id:
        html = get(f"/bookings/{booking_id}")
        check("detail shows pending state",
              "Vehicle & Driver Allocation Pending" in html
              or "Vehicle &amp; Driver Allocation Pending" in html)

        # Step 2: vendor (auto-detected lead flag needs confirm_lead for Dec 31 pickup)
        html = post(f"/bookings/{booking_id}/allocate/vendor", {
            "vendor_name": "Smoke Vendor", "vendor_contact": "9888888888",
            "vendor_email": "vendor@example.com", "vendor_pkg_type": "8 Hrs / 80 Kms",
            "confirm_lead": "1",
        })
        check("step 2 vendor allocated", "Awaiting Driver &amp; Vehicle Allocation" in html
              or "Awaiting Driver & Vehicle Allocation" in html)

        # Step 3: driver + vehicle
        html = post(f"/bookings/{booking_id}/allocate/driver", {
            "driver_name": "Smoke Driver", "driver_contact": "9777777777",
            "vehicle_no": "TS01AB1234", "driver_reporting_time": "09:45 AM",
        })
        check("step 3 confirmed", "Booking Confirmed - Driver &amp; Vehicle Allocated" in html
              or "Booking Confirmed - Driver & Vehicle Allocated" in html)

        # Dual-confirmation trip lifecycle
        html = post(f"/bookings/{booking_id}/trip/start-guest", {})
        check("guest starts trip", "Guest Trip Started" in html)
        html = post(f"/bookings/{booking_id}/trip/start-driver", {})
        check("driver starts trip", "Trip In Progress" in html)
        html = post(f"/bookings/{booking_id}/trip/end-guest", {})
        check("guest ends trip", "Guest Trip Ended" in html)
        html = post(f"/bookings/{booking_id}/trip/end-driver", {})
        check("driver ends trip -> completed", "Trip Completed" in html)
        m = re.search(r"INV-(\d+)", html)
        check("provisional invoice generated", bool(m))
        invoice_id = f"INV-{m.group(1)}" if m else ""

        if invoice_id:
            html = get(f"/invoices/{invoice_id}")
            check("invoice detail renders (ratecard original amount)",
                  "Original Amount" in html)
            html = post(f"/invoices/{invoice_id}/submit-expenses", {
                "toll": "100", "parking": "50", "extra_kms": "200",
                "extra_hours": "0", "other_expenses": "0",
            })
            check("vendor expenses -> final invoice", "Final Invoice" in html)
            html = post("/payments/record", {
                "pay_type": "Receipt from Customer", "ref_id": invoice_id,
                "counterparty": "Smoke Test Co", "amount": "350",
                "pay_method": "UPI", "pay_status": "Completed",
            })
            check("payment recorded against invoice", "Payment Received" in html
                  or "Partially Paid" in html)

    # --- cancellation (second dummy booking) ---
    html = post("/bookings/create", {
        "booking_type": "Dummy", "company_name": "Smoke Test Co",
        "guest_name": "Cancel Guest", "pickup_address": "A", "pickup_city": "Pune",
        "pickup_date": "31-12-2026", "pickup_time": "10:00 AM",
        "drop_address": "B", "drop_city": "Mumbai",
    })
    m = re.search(r"DM-(\d+)", html)
    if m:
        cancel_id = f"DM-{m.group(1)}"
        html = post(f"/bookings/{cancel_id}/cancel", {"reason_code": "1", "confirm": "1"})
        check("cancellation -> 3-Cancelled + invoice",
              "3-Cancelled" in html and "Cancellation" in html)

    # --- payments & dashboards ---
    html = get("/payments")
    check("payments list renders", "Payments" in html)
    html = get("/dashboards")
    for page, marker in [
        ("/dashboards/home", "Dashboard KPIs"),
        ("/dashboards/ops", "Ops Dashboard"),
        ("/dashboards/tracking", "Tracking Dashboard"),
        ("/dashboards/finance", "Finance Dashboard"),
        ("/dashboards/sales", "Sales Dashboard"),
        ("/dashboards/vendor", "Vendor Dashboard"),
        ("/dashboards/customer360", "Customer 360"),
        ("/dashboards/investor", "Investor MIS"),
        ("/dashboards/compliance", "Compliance"),
    ]:
        try:
            html = get(page)
            check(f"{page} renders", marker in html)
        except urllib.error.HTTPError as e:
            check(f"{page} renders", False, f"HTTP {e.code}")
    html = post("/dashboards/sla-check", {})
    check("SLA check runs", "SLA check executed" in html or "SLA Alerts" in html)

    # --- masters autocomplete endpoints ---
    for ep in ("/bookings/vendors?q=sm", "/bookings/drivers?q=sm", "/bookings/vehicles?q=ts"):
        try:
            get(ep)
            check(f"autocomplete {ep}", True)
        except urllib.error.HTTPError as e:
            check(f"autocomplete {ep}", False, f"HTTP {e.code}")

    # --- logout + login-log ---
    html = get("/auth/logout")
    check("logout", "signed out" in html.lower() or "Login" in html)

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    import urllib.error  # noqa: E402
    main()
