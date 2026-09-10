"""Booking routes: list, create (Step 1), and update booking status."""

import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, time
from urllib.parse import quote

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates

from ..auth import current_user, module_level
from ..templating import templates
from ..db import get_connection, multi_fetch
from ..config import settings
from ..scope import (
    visible_booking_ids, can_view, OPERATOR_ROLES,
    CORPORATE_PORTAL_ROLES, VENDOR_PORTAL_ROLES,
)
from ..gps import sync_status_text, gps_report, distance_meters, route_estimate, route_estimate_multi
from ..audit import audit, _parse_oracle_dt
from ..notification_scope import can_see_notification
from ..device import is_mobile_request
from ..feedback_rules import owner_group
from ..location_service import location_service
from ..sla_engine import emit_start, complete_for_entity
from ..rates import customer_rate
from .. import sla
from .. import notify
from ..ids import (
    next_company_id, next_employee_ids, next_individual_id,
    next_guest_company_id, next_vendor_id, next_driver_id, next_vehicle_id,
)

router = APIRouter(prefix="/bookings")

# Roles that may perform allocation (Steps 2-3: vendor + driver/vehicle).
# Everyone else can view, but only Ops/Vendor Manager/Corporate Admin/Vendor
# can assign a vendor or confirm the driver & vehicle allocation.
ALLOCATOR_ROLES = set(OPERATOR_ROLES) | {
    "vendor manager", "vendor", "vendor admin", "vendor operations",
}

# Cancellation policy (SOP section 6.1): code -> (description, charge Rs.)
CANCELLATION_POLICY = {
    1: ("After Step 1, before Step 3 - booking cancelled by guest", 0.0),
    2: ("After Step 3, more than 6 hours before pickup", 0.0),
    3: ("After Step 3, less than 6 hours before pickup", 500.0),
    4: ("Cab reached pickup, guest no-show", 1000.0),
    5: ("Cab did not reach pickup on time (vendor fault)", 0.0),
    6: ("Cab breakdown during ongoing trip", 0.0),
}
CANCELLATION_POLICY_TEXT = (
    "1: After Step 1 before Step 3 (guest cancel) - Rs.0 | "
    "2: After Step 3, 6+ hrs before pickup - Rs.0 | "
    "3: After Step 3, under 6 hrs before pickup - Rs.500 | "
    "4: Cab reached, guest no-show - Rs.1000 | "
    "5: Cab did not reach on time (vendor fault) - Rs.0 | "
    "6: Cab breakdown during ongoing trip - Rs.0"
)


def _can_allocate(user):
    role = (user.get("role") or "").strip().lower()
    if role in CORPORATE_PORTAL_ROLES:
        return False
    if role in VENDOR_PORTAL_ROLES:
        return role != "vendor viewer"
    # Internal RentaGO users are controlled by the Roles Matrix. This keeps
    # Finance/Operations/etc. consistent with their explicit Bookings access.
    return role in ALLOCATOR_ROLES or module_level(user, "Bookings") == "F"


def _is_corporate(user):
    return (user.get("role") or "").strip().lower() in CORPORATE_PORTAL_ROLES


def _is_vendor_portal(user):
    return (user.get("role") or "").strip().lower() in VENDOR_PORTAL_ROLES


def _can_modify_booking(user):
    # Step 1 is editable by Corporate and internal RentaGO users only.
    return _is_corporate(user) or (
        not _is_vendor_portal(user) and _can_allocate(user)
    )


def _can_change_driver(user):
    return _can_allocate(user)


def _can_change_vendor(user):
    return _can_allocate(user) and not _is_vendor_portal(user)


def _is_rentago_override(user):
    role = (user.get("role") or "").strip().lower()
    return role not in CORPORATE_PORTAL_ROLES | VENDOR_PORTAL_ROLES | {"guest", "driver"}


def _rentago_operator_present(cur):
    """Require a recently active internal RentaGO session for participant actions."""
    cur.execute(
        "SELECT COUNT(1) FROM user_sessions s JOIN users u ON UPPER(u.user_id)=UPPER(s.user_id) "
        "WHERE u.status='Active' AND LOWER(u.role) NOT IN "
        "('super admin','corporate admin','corporate booking user','corporate manager','corporate viewer'," 
        "'vendor','vendor admin','vendor operations','vendor viewer','guest','driver') "
        "AND s.last_activity >= SYSDATE-(5/1440)")
    return int(cur.fetchone()[0] or 0) > 0


def _driver_matches_booking(user, booking):
    name = (user.get("name") or "").strip().lower()
    mobile = (user.get("mobile") or "").strip().lower()
    return ((name and name == (booking.get("driver_name") or "").strip().lower())
            or (mobile and mobile == (booking.get("driver_contact") or "").strip().lower()))


def _can_guest_trip_action(user):
    return _is_rentago_override(user) or _is_corporate(user) or (
        (user.get("role") or "").strip().lower() == "guest"
    )


def _participant_mobile_only(request, user):
    return ((user.get("role") or "").strip().lower() in {"guest", "driver"}
            and not is_mobile_request(request))


def _can_driver_trip_action(user, booking):
    return _is_rentago_override(user) or (
        (user.get("role") or "").strip().lower() == "driver"
        and _driver_matches_booking(user, booking)
    )


def _gps_pair(value):
    """Parse a captured `lat, lon` value and reject invalid coordinates."""
    try:
        lat, lon = (float(part.strip()) for part in (value or "").split(",", 1))
    except (TypeError, ValueError):
        return None, None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None, None
    return lat, lon


def _geocode_address(address, city, state, country):
    """Resolve a booking address when the form did not already capture GPS."""
    query = ", ".join(x.strip() for x in (address, city, state, country) if x and x.strip())
    if len(query) < 3:
        return None, None, "Unavailable"
    results = location_service.geocode(query)
    if results:
        return results[0].lat, results[0].lon, results[0].provider
    return None, None, "Unavailable"


def _planned_stops(pickup_address, pickup_city, pickup_state, pickup_country, pickup_gps,
                   pickup_points, drop_address, drop_city, drop_state, drop_country,
                   drop_gps, drop_points):
    """Build the ordered pickup -> intermediate -> drop route and geocode stops."""
    stops = []

    def add(label, address, city, state, country, gps):
        if not (address or "").strip() and not (gps or "").strip():
            return
        lat, lon = _gps_pair(gps)
        provider = "Captured GPS" if lat is not None else ""
        if lat is None:
            lat, lon, provider = _geocode_address(address, city, state, country)
        stops.append({"label": label, "address": (address or "").strip(),
                      "lat": lat, "lon": lon, "provider": provider})

    add("Pickup", pickup_address, pickup_city, pickup_state, pickup_country, pickup_gps)
    for index, item in enumerate(pickup_points, 1):
        point, gps = item if isinstance(item, tuple) else (item, "")
        add(f"Pickup {index}", point, pickup_city, pickup_state, pickup_country, gps)
    for index, item in enumerate(drop_points, 1):
        point, gps = item if isinstance(item, tuple) else (item, "")
        add(f"Drop {index}", point, drop_city, drop_state, drop_country, gps)
    add("Drop", drop_address, drop_city, drop_state, drop_country, drop_gps)
    return stops


def _planned_route_payload(stops, legs):
    """Keep route JSON compact enough for Oracle SQL*Plus fallback reads."""
    compact_stops = [{"label": s.get("label"), "lat": s.get("lat"), "lon": s.get("lon"),
                      "provider": s.get("provider")} for s in stops]
    return json.dumps({"stops": compact_stops, "legs": legs}, separators=(",", ":"), default=str)


def _next_booking_id(conn, booking_type: str) -> str:
    """Generate next booking id per type (mirrors GetNextBookingID / GetNextDummyID)."""
    btype = (booking_type or "").lower()
    if "individual" in btype:
        prefix, base = "IN-", 900000
    elif "dummy" in btype:
        prefix, base = "DM-", 100000
    else:
        prefix, base = "BK-", 900000
    cur = conn.cursor()
    cur.execute(
        "SELECT booking_id FROM bookings WHERE booking_id LIKE :1", (prefix + "%",)
    )
    max_num = base
    for (bid,) in cur.fetchall():
        try:
            num = int(bid.split("-")[1])
            if num > max_num:
                max_num = num
        except Exception:
            pass
    return f"{prefix}{max_num + 1}"


def _next_trip_id(conn) -> str:
    """Generate the next trip id, mirroring the VBA GetNextTripID (base 700000)."""
    cur = conn.cursor()
    cur.execute("SELECT trip_id FROM trips")
    max_num = 700000
    for (tid,) in cur.fetchall():
        s = str(tid or "").strip()
        if s.startswith("TR-"):
            try:
                n = int(s[3:])
                if n > max_num:
                    max_num = n
            except Exception:
                pass
    return f"TR-{max_num + 1}"


def _search_guests(conn, query: str, limit: int = 20) -> list:
    """Search a merged Employees + Individuals guest list by name/company/phone.

    Returns everything the booking form needs to auto-fill on selection:
    guest identity + contact, company name/id, the company's legal name (used
    as the Entity Name) and the admin contact trio.
    """
    q = f"%{(query or '').strip()}%"
    if not query.strip():
        q = "%"
    cur = conn.cursor()
    cur.execute(
        """SELECT guest_name, guest_mobile, company_name, company_id, emp_code,
                  guest_email, admin_name, admin_mobile, admin_email,
                  'Employee' AS source
           FROM employees
           WHERE (status IS NULL OR UPPER(status)='ACTIVE')
             AND (LOWER(guest_name) LIKE LOWER(:1) OR LOWER(company_name) LIKE LOWER(:2)
                  OR guest_mobile LIKE :3)
           UNION ALL
           SELECT guest_name, guest_contact, company_name, company_id, NULL,
                  guest_email, admin_name, admin_contact, admin_email,
                  'Individual' AS source
           FROM individuals
           WHERE (status IS NULL OR UPPER(status)='ACTIVE')
             AND (LOWER(guest_name) LIKE LOWER(:4) OR LOWER(company_name) LIKE LOWER(:5)
                  OR guest_contact LIKE :6)""",
        (q, q, q, q, q, q),
    )
    rows = cur.fetchall()
    # resolve entity names (companies.legal_name) for the matched companies in
    # one extra query so the form can auto-fill Entity Name
    cids = sorted({str(r[3]).strip() for r in rows if r[3] and str(r[3]).strip()})
    entity = {}
    if cids:
        in_list = ", ".join(f":{i + 1}" for i in range(len(cids)))
        cur.execute(
            f"SELECT company_id, legal_name FROM companies "
            f"WHERE company_id IN ({in_list})",
            cids,
        )
        entity = {str(c).strip(): (l or "") for c, l in cur.fetchall()}
    out = []
    for r in rows:
        if not r[0]:
            continue
        cid = str(r[3] or "").strip()
        out.append({
            "guest_name": r[0], "mobile": r[1], "company": r[2],
            "company_id": cid or "", "code": r[4], "email": r[5],
            "admin_name": r[6] or "", "admin_mobile": r[7] or "",
            "admin_email": r[8] or "", "source": r[9],
            "entity": entity.get(cid, ""),
        })
        if len(out) >= limit:
            break
    return out


@router.get("/guests")
def search_guests(request: Request, q: str = ""):
    user = current_user(request)
    if not user:
        return JSONResponse([], status_code=401)
    conn = get_connection()
    try:
        results = _search_guests(conn, q)
    finally:
        conn.close()
    return JSONResponse(results)


@router.get("/companies")
def search_companies(request: Request, q: str = ""):
    """JSON autocomplete over the Companies master (booking form Step 1).

    On pick the form fills Company Name, Company Id and Entity Name (legal name).
    """
    user = current_user(request)
    if not user:
        return JSONResponse([], status_code=401)
    query = f"%{(q or '').strip()}%"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT company_id, company_name, legal_name, city, state "
        "FROM companies WHERE LOWER(company_name) LIKE LOWER(:1) "
        "AND (status IS NULL OR UPPER(status)='ACTIVE') "
        "ORDER BY company_name",
        (query,),
    )
    rows = cur.fetchall()[:20]
    conn.close()
    return JSONResponse([
        {"company_id": r[0], "company_name": r[1], "entity": r[2] or "",
         "city": r[3] or "", "state": r[4] or ""}
        for r in rows if r[1]
    ])


@router.get("/company-entities")
def company_entities(request: Request, company_id: str = ""):
    user = current_user(request)
    if not user or not company_id.strip():
        return JSONResponse([], status_code=401 if not user else 200)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT entity_id,entity_code,legal_name,gstin,city,state,address FROM company_entities WHERE company_id=:1 AND (status IS NULL OR UPPER(status)='ACTIVE') ORDER BY legal_name", (company_id.strip(),))
    rows = [{"entity_id": r[0], "entity_code": r[1] or "", "legal_name": r[2], "gstin": r[3] or "", "city": r[4] or "", "state": r[5] or "", "address": r[6] or ""} for r in cur.fetchall()]
    if not rows:
        cur.execute("SELECT company_id,legal_name,city,state FROM companies WHERE company_id=:1", (company_id.strip(),))
        legacy = cur.fetchone()
        if legacy and legacy[1]:
            rows = [{"entity_id": "LEGACY-" + str(legacy[0]), "entity_code": "LEGACY", "legal_name": legacy[1], "gstin": "", "city": legacy[2] or "", "state": legacy[3] or "", "address": ""}]
    conn.close()
    return JSONResponse(rows)


@router.get("/geocode")
def geocode(request: Request, q: str = ""):
    """GPS lookup for Pickup/Drop addresses via OpenStreetMap Nominatim
    (free, no API key). The query follows the sequence
    Location Address, City, State, Country - e.g.
    /bookings/geocode?q=Hinjewadi Phase 2, Pune, Maharashtra, India
    Returns [{display_name, lat, lon}] or {error}.
    """
    user = current_user(request)
    if not user:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    query = (q or "").strip()
    if len(query) < 3:
        return JSONResponse({"error": "query too short"})
    try:
        return JSONResponse([result.__dict__ for result in location_service.geocode(query)])
    except Exception as exc:
        return JSONResponse({"error": f"map lookup failed: {exc}"})


@router.get("/vendors")
def search_vendors(request: Request, q: str = ""):
    """JSON autocomplete over the Vendors master (Step 2 pick list)."""
    user = current_user(request)
    if not user:
        return JSONResponse([], status_code=401)
    query = f"%{(q or '').strip()}%"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT vendor_name, mobile, email FROM vendors "
        "WHERE (LOWER(vendor_name) LIKE LOWER(:1) OR LOWER(email) LIKE LOWER(:2)) "
        "AND (status IS NULL OR UPPER(status) NOT IN ('INACTIVE','BLACKLISTED')) "
        "ORDER BY vendor_name",
        (query, query),
    )
    rows = cur.fetchall()[:20]
    conn.close()
    return JSONResponse([
        {"name": r[0], "contact": r[1], "email": r[2]} for r in rows if r[0]
    ])


@router.get("/drivers")
def search_drivers(request: Request, q: str = ""):
    """JSON autocomplete over the Drivers master (Step 3 pick list)."""
    user = current_user(request)
    if not user:
        return JSONResponse([], status_code=401)
    query = f"%{(q or '').strip()}%"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT driver_name, mobile FROM drivers "
        "WHERE (LOWER(driver_name) LIKE LOWER(:1) OR mobile LIKE :2) "
        "AND (status IS NULL OR UPPER(status) NOT IN ('INACTIVE','TERMINATED')) "
        "ORDER BY driver_name",
        (query, query),
    )
    rows = cur.fetchall()[:20]
    conn.close()
    return JSONResponse([
        {"name": r[0], "contact": r[1]} for r in rows if r[0]
    ])


@router.get("/vehicles")
def search_vehicles(request: Request, q: str = ""):
    """JSON autocomplete over the Vehicles master (Step 3 pick list)."""
    user = current_user(request)
    if not user:
        return JSONResponse([], status_code=401)
    query = f"%{(q or '').strip()}%"
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT reg_number, category FROM vehicles "
        "WHERE (UPPER(reg_number) LIKE UPPER(:1) OR LOWER(category) LIKE LOWER(:2)) "
        "AND (status IS NULL OR UPPER(status) NOT IN ('INACTIVE','SCRAPPED')) "
        "ORDER BY reg_number",
        (query, query),
    )
    rows = cur.fetchall()[:20]
    conn.close()
    return JSONResponse([
        {"reg": r[0], "category": r[1]} for r in rows if r[0]
    ])


@router.get("")
def list_bookings(
    request: Request, status: str = "",
    f_company_name: str = "", f_entity_name: str = "", f_guest_name: str = "",
    f_pickup_address: str = "", f_drop_address: str = "",
    f_pickup_city: str = "", f_drop_city: str = "",
    f_pickup_date: str = "", f_pickup_time: str = "",
    f_vehicle_type: str = "", page: int = 1,
):
    """Booking list with per-field search filters (AND-ed together):

    company, entity name, any guest name (1-5), pickup/drop address,
    pickup/drop city, pickup date & time, vehicle type and status.
    """
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if (user.get("role") or "").strip().lower() in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}:
        return RedirectResponse(url="/dashboards/vendor", status_code=303)
    if module_level(user, "Bookings") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    alerts = sla.maybe_sweep(user)
    conn = get_connection()
    cur = conn.cursor()
    sql = (
        "SELECT booking_id, booking_date, booking_type, company_name, entity_name, "
        "guest_name_1, pickup_address, drop_address, pickup_city, drop_city, "
        "pickup_date, pickup_time, vehicle_type, booking_status, status_reason, "
        "driver_name, driver_contact, vehicle_no, vendor_name, vendor_contact, vendor_email, "
        "vendor_pkg_type, "
        "NVL((SELECT NVL((SELECT e.emp_id FROM employees e WHERE UPPER(TRIM(e.company_name))=UPPER('RentaGO Technologies Pvt Ltd') AND UPPER(TRIM(e.guest_name))=UPPER(TRIM(u.name)) AND ROWNUM=1),NVL(u.emp_id,u.user_id))||' Name: '||NVL(u.name,u.user_id) FROM users u WHERE UPPER(u.user_id)=UPPER(b.done_by_booking)), b.done_by_booking), "
        "NVL((SELECT NVL((SELECT e.emp_id FROM employees e WHERE UPPER(TRIM(e.company_name))=UPPER('RentaGO Technologies Pvt Ltd') AND UPPER(TRIM(e.guest_name))=UPPER(TRIM(u.name)) AND ROWNUM=1),NVL(u.emp_id,u.user_id))||' Name: '||NVL(u.name,u.user_id) FROM users u WHERE UPPER(u.user_id)=UPPER(b.done_by_vendor)), b.done_by_vendor), "
        "NVL((SELECT NVL((SELECT e.emp_id FROM employees e WHERE UPPER(TRIM(e.company_name))=UPPER('RentaGO Technologies Pvt Ltd') AND UPPER(TRIM(e.guest_name))=UPPER(TRIM(u.name)) AND ROWNUM=1),NVL(u.emp_id,u.user_id))||' Name: '||NVL(u.name,u.user_id) FROM users u WHERE UPPER(u.user_id)=UPPER(b.done_by_driver)), b.done_by_driver), "
        "guest_contact FROM bookings b"
    )

    params, conds = [], []
    if user.get("tenant_id") and (user.get("role") or "").strip().lower() != "super admin":
        params.append(user["tenant_id"])
        conds.append(f"b.tenant_id=:{len(params)}")

    def _like(col, val):
        v = (val or "").strip()
        if not v:
            return
        params.append("%" + v + "%")
        conds.append(f"LOWER(NVL({col}, ' ')) LIKE LOWER(:{len(params)})")

    _like("booking_status", status)
    _like("company_name", f_company_name)
    _like("entity_name", f_entity_name)
    if (f_guest_name or "").strip():
        v = f_guest_name.strip()
        ors = []
        for c in ("guest_name_1", "guest_name_2", "guest_name_3",
                  "guest_name_4", "guest_name_5"):
            params.append("%" + v + "%")
            ors.append(f"LOWER(NVL({c}, ' ')) LIKE LOWER(:{len(params)})")
        conds.append("(" + " OR ".join(ors) + ")")
    _like("pickup_address", f_pickup_address)
    _like("drop_address", f_drop_address)
    _like("pickup_city", f_pickup_city)
    _like("drop_city", f_drop_city)
    if (f_pickup_date or "").strip():
        v = f_pickup_date.strip()
        params.append("%" + v + "%")
        n = len(params)
        conds.append(
            f"(TO_CHAR(pickup_date, 'DD-MM-YYYY') LIKE :{n} "
            f"OR TO_CHAR(pickup_date, 'YYYY-MM-DD') LIKE :{n})")
    _like("pickup_time", f_pickup_time)
    _like("vehicle_type", f_vehicle_type)

    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY booking_date DESC NULLS LAST, booking_id DESC FETCH FIRST 500 ROWS ONLY"
    cur.execute(sql, params or None)
    rows = cur.fetchall()

    visible = visible_booking_ids(user, cur)
    conn.close()

    bookings = []
    for r in rows:
        if not can_view(visible, str(r[0])):
            continue
        has_driver = bool(r[15])
        has_vendor = bool(r[17])
        if has_driver:
            step = "3"
        elif has_vendor:
            step = "2"
        else:
            step = "1"
        step1_state = "1-Booked" if r[13] and not str(r[13]).startswith("1-") else "1-Pending"
        step2_state = "2-Allocated" if has_vendor else "2-Pending"
        step3_state = "3-Confirmed" if has_driver and str(r[13]) == "2-Confirmed" else ("3-Allocated" if has_driver else "3-Pending")
        if str(r[13] or "").startswith("3-"):
            step3_state = "3-Cancelled"
        status_display = str(r[13] or "1-Pending")
        status_class = "bg-danger" if status_display.startswith("3-") else ("bg-success" if status_display.startswith("2-") else "bg-warning text-dark")
        bookings.append({
            "booking_id": r[0], "booking_date": r[1], "booking_type": r[2],
            "company_name": r[3], "entity_name": r[4], "guest_name": r[5],
            "pickup_address": r[6], "drop_address": r[7],
            "pickup_city": r[8], "drop_city": r[9],
            "pickup_date": r[10], "pickup_time": r[11],
            "vehicle_type": r[12], "status": r[13], "reason": r[14],
            "driver_name": r[15], "driver_contact": r[16], "vehicle_no": r[17],
            "vendor_name": r[18],
            "vendor_contact": r[19],
            "vendor_email": r[20],
            "vendor_pkg_type": r[21],
            "step": step,
            "step1_state": step1_state, "step2_state": step2_state,
            "step3_state": step3_state,
            "status_display": status_display, "status_class": status_class,
            "booked_by_step1": r[22] or "-", "booked_by_step2": r[23] or "-",
            "booked_by_step3": r[24] or "-",
            "guest_contact": r[25] or "-",
        })
    total_count = len(bookings)
    page_size = 10
    page = max(1, page)
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    page = min(page, total_pages)
    bookings = bookings[(page - 1) * page_size:page * page_size]
    base_query = urllib.parse.urlencode({k: v for k, v in request.query_params.multi_items() if k != "page"})
    filters = [
        {"name": "f_company_name", "label": "Company", "value": f_company_name.strip()},
        {"name": "f_entity_name", "label": "Entity Name", "value": f_entity_name.strip()},
        {"name": "f_guest_name", "label": "Guest Name (any of 1-5)",
         "value": f_guest_name.strip()},
        {"name": "f_pickup_address", "label": "Pickup Address", "value": f_pickup_address.strip()},
        {"name": "f_drop_address", "label": "Drop Address", "value": f_drop_address.strip()},
        {"name": "f_pickup_city", "label": "Pickup City", "value": f_pickup_city.strip()},
        {"name": "f_drop_city", "label": "Drop City", "value": f_drop_city.strip()},
        {"name": "f_pickup_date", "label": "Pickup Date (DD-MM-YYYY)", "value": f_pickup_date.strip()},
        {"name": "f_pickup_time", "label": "Pickup Time", "value": f_pickup_time.strip()},
        {"name": "f_vehicle_type", "label": "Vehicle Type", "value": f_vehicle_type.strip()},
    ]
    return templates.TemplateResponse(
        "bookings/list.html",
        {"request": request, "user": user, "bookings": bookings,
         "status_filter": status.strip(), "filters": filters,
         "sla_alerts": alerts, "page": page, "total_pages": total_pages,
         "total_count": total_count, "base_query": base_query,
         "show_vendor_name": _is_rentago_override(user)},
    )


def _resolve_or_create_company_id(cur, company_name):
    """Resolve a company ID by name (case-insensitive). If missing, create it.
    Mirrors VBA CompanyNameChanged: company found by Companies col3 name, but the
    user prefers auto-creating the company (ID convention 'C0xx')."""
    cur.execute(
        "SELECT company_id FROM companies WHERE UPPER(TRIM(company_name))=UPPER(TRIM(:1))",
        (company_name,),
    )
    row = cur.fetchone()
    if row:
        return str(row[0])
    cid = next_company_id(cur)
    cur.execute(
        "INSERT INTO companies (company_id, company_name, status) VALUES (:1,:2,'Active')",
        (cid, company_name),
    )
    return cid


def _save_new_employee(cur, company_name, company_id, guest_name, f):
    """Mirror VBA SaveNewEmployee: dedup by exact company+guest, else insert a new
    Employees row with emp_id=AKP-<n> / emp_code=RG-<n> (matching existing data)."""
    if not company_name or not guest_name:
        return False
    cur.execute(
        "SELECT emp_code FROM employees WHERE UPPER(TRIM(company_name))=UPPER(TRIM(:1)) "
        "AND UPPER(TRIM(guest_name))=UPPER(TRIM(:2))",
        (company_name, guest_name),
    )
    if cur.fetchone():
        return False
    emp_id, emp_code = next_employee_ids(cur)
    cur.execute(
        """INSERT INTO employees (
            emp_id, company_name, company_id, emp_code, guest_name, guest_mobile,
            guest_email, admin_name, admin_mobile, admin_email, pickup_location,
            drop_location, status
        ) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,'Active')""",
        (emp_id, company_name, company_id, emp_code, guest_name,
         f.get("guest_contact"), f.get("guest_email"), f.get("admin_name"),
         f.get("admin_contact"), f.get("admin_email"), f.get("pickup_address"),
         f.get("drop_address")),
    )
    return True


def _save_individual_booking(cur, booking_id, booking_type, guest_name, f):
    """Mirror VBA SaveIndividualBooking: update matching individual (name+type) else
    insert new Individuals row (individual_id = IND-<max+1>).

    A NEW guest name automatically gets a new Company ID 'RG-<n>' (+1 over the
    last RG- number in the system database) unless a company id was already
    picked from the autocomplete."""
    if not guest_name:
        return False
    cur.execute(
        "SELECT individual_id FROM individuals WHERE UPPER(TRIM(guest_name))=UPPER(TRIM(:1)) "
        "AND UPPER(booking_type) IN ('INDIVIDUAL','INDIVIDUAL EVENT')",
        (guest_name,),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            """UPDATE individuals SET guest_contact=:1, guest_email=:2, pickup_location=:3,
            drop_location=:4, created_date=:5, booking_type=:6 WHERE individual_id=:7""",
            (f.get("guest_contact"), f.get("guest_email"), f.get("pickup_address"),
             f.get("drop_address"), datetime.now(), booking_type, str(row[0])),
        )
        return False
    ind_id = next_individual_id(cur, f.get("company_id"))
    # auto Company ID: RG-<n>, +1 over the last RG- in the system
    company_id = (str(f.get("company_id") or "").strip()
                  or next_guest_company_id(cur))
    cur.execute(
        """INSERT INTO individuals (
            individual_id, company_name, company_id, booking_id, guest_name,
            guest_contact, guest_email, admin_name, admin_contact, admin_email,
            pickup_location, drop_location, created_date, status, done_by, booking_type
        ) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13,'Active',:14,:15)""",
        (ind_id, f.get("company_name"), company_id, booking_id, guest_name,
         f.get("guest_contact"), f.get("guest_email"), f.get("admin_name"),
         f.get("admin_contact"), f.get("admin_email"), f.get("pickup_address"),
         f.get("drop_address"), datetime.now(), f.get("done_by"), booking_type),
    )
    return True


def _save_booking_guest(conn, cur, booking_type, booking_id, f):
    """Mirror VBA SubmitBooking1: individual/individual event -> SaveIndividualBooking,
    else -> SaveNewEmployee."""
    bt = (booking_type or "").strip().lower()
    if bt in ("individual", "individual event"):
        return _save_individual_booking(cur, booking_id, booking_type, f.get("guest_name"), f)
    if bt == "dummy":
        return False
    if f.get("company_name"):
        company_id = _resolve_or_create_company_id(cur, f.get("company_name"))
        f["company_id"] = company_id
        return _save_new_employee(cur, f.get("company_name"), company_id, f.get("guest_name"), f)
    return False


@router.post("/create")
def create_booking(
    request: Request,
    booking_type: str = Form(""),
    company_name: str = Form(""),
    entity_name: str = Form(""),
    reference_code: str = Form(""),
    ref_no: str = Form(""),
    guest_name: str = Form(""),
    guest_name_2: str = Form(""),
    guest_name_3: str = Form(""),
    guest_name_4: str = Form(""),
    guest_name_5: str = Form(""),
    emp_guest_id: str = Form(""),
    guest_email: str = Form(""),
    guest_contact: str = Form(""),
    admin_name: str = Form(""),
    admin_email: str = Form(""),
    admin_contact: str = Form(""),
    email_received: str = Form(""),
    email_sent: str = Form(""),
    request_received_time: str = Form(""),
    company_id: str = Form(""),
    pickup_address: str = Form(""),
    pickup_city: str = Form(""),
    pickup_state: str = Form(""),
    pickup_country: str = Form("India"),
    pickup_gps: str = Form(""),
    pickup_manual_address: str = Form(""),
    pickup_gps_link: str = Form(""),
    pickup_lat: str = Form(""),
    pickup_lon: str = Form(""),
    pickup_date: str = Form(""),
    pickup_time: str = Form(""),
    pickup_1: str = Form(""),
    pickup_2: str = Form(""),
    pickup_3: str = Form(""),
    pickup_4: str = Form(""),
    pickup_5: str = Form(""),
    pickup_1_gps: str = Form(""), pickup_2_gps: str = Form(""), pickup_3_gps: str = Form(""),
    pickup_4_gps: str = Form(""), pickup_5_gps: str = Form(""),
    no_of_guests: str = Form(""),
    pickups_sm: str = Form(""),
    drops_sm: str = Form(""),
    drop_address: str = Form(""),
    drop_city: str = Form(""),
    drop_state: str = Form(""),
    drop_country: str = Form("India"),
    drop_gps: str = Form(""),
    drop_manual_address: str = Form(""),
    drop_gps_link: str = Form(""),
    drop_lat: str = Form(""),
    drop_lon: str = Form(""),
    drop_date: str = Form(""),
    drop_time: str = Form(""),
    drop_1: str = Form(""),
    drop_2: str = Form(""),
    drop_3: str = Form(""),
    drop_4: str = Form(""),
    drop_5: str = Form(""),
    drop_1_gps: str = Form(""), drop_2_gps: str = Form(""), drop_3_gps: str = Form(""),
    drop_4_gps: str = Form(""), drop_5_gps: str = Form(""),
    vehicle_type: str = Form(""),
    package_type: str = Form(""),
    area_code: str = Form(""),
    flight_details: str = Form(""),
    driver_reporting_time: str = Form(""),
    # Package type options (VBA parity): Per Day, Multiple Days, and free-form.
    # The form accepts any string; operators should select one of:
    #   "Per Day", "Multiple Days", or a custom description (e.g. "8 Hrs / 80 Kms").
):
    """Step 1: full BookingForm parity (VBA WriteBookingRow B5-B53 -> cols)."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)

    conn = get_connection()
    booking_id = _next_booking_id(conn, booking_type)
    cur = conn.cursor()

    # shared parsers (module level) - also used by the modify/edit routes
    to_date, to_dt, s = _to_date, _to_dt, _s
    pickup_lat_val, pickup_lon_val = _gps_pair(pickup_gps)
    drop_lat_val, drop_lon_val = _gps_pair(drop_gps)
    if pickup_lat_val is None:
        pickup_lat_val, pickup_lon_val, _ = _geocode_address(
            pickup_address, pickup_city, pickup_state, pickup_country)
        if pickup_lat_val is not None:
            pickup_gps = f"{pickup_lat_val}, {pickup_lon_val}"
            pickup_gps_link = f"https://www.google.com/maps?q={pickup_gps}"
    if drop_lat_val is None:
        drop_lat_val, drop_lon_val, _ = _geocode_address(
            drop_address, drop_city, drop_state, drop_country)
        if drop_lat_val is not None:
            drop_gps = f"{drop_lat_val}, {drop_lon_val}"
            drop_gps_link = f"https://www.google.com/maps?q={drop_gps}"
    planned_stops = _planned_stops(
        pickup_address, pickup_city, pickup_state, pickup_country, pickup_gps,
        [(pickup_1, pickup_1_gps), (pickup_2, pickup_2_gps), (pickup_3, pickup_3_gps), (pickup_4, pickup_4_gps), (pickup_5, pickup_5_gps)],
        drop_address, drop_city, drop_state, drop_country, drop_gps,
        [(drop_1, drop_1_gps), (drop_2, drop_2_gps), (drop_3, drop_3_gps), (drop_4, drop_4_gps), (drop_5, drop_5_gps)])
    planned_kms, planned_hrs, planned_source, planned_legs = route_estimate_multi(planned_stops)
    planned_route_json = _planned_route_payload(planned_stops, planned_legs)

    values = {
        "booking_id": booking_id, "tenant_id": user.get("tenant_id") or "TEN-RENTA-GO",
        "booking_date": to_date(datetime.now().strftime("%d-%m-%Y")),
        "booking_type": s(booking_type), "company_name": s(company_name),
        "company_id": s(company_id),
        "entity_name": s(entity_name),
        "guest_name_1": s(guest_name), "guest_name_2": s(guest_name_2),
        "guest_name_3": s(guest_name_3), "guest_name_4": s(guest_name_4),
        "guest_name_5": s(guest_name_5), "emp_guest_id": s(emp_guest_id),
        "guest_email": s(guest_email), "guest_contact": s(guest_contact),
        "admin_name": s(admin_name), "admin_email": s(admin_email),
        "admin_contact": s(admin_contact),
        "email_received": s(email_received), "email_sent": s(email_sent),
        "request_received_time": to_dt(request_received_time),
        "pickup_address": s(pickup_address), "pickup_city": s(pickup_city),
        "pickup_state": s(pickup_state), "pickup_date": to_date(pickup_date),
        "pickup_time": s(pickup_time), "pickup_gps": s(pickup_gps),
        "pickup_lat": pickup_lat_val, "pickup_lon": pickup_lon_val,
        "pickup_manual_address": s(pickup_manual_address) or s(pickup_address),
        "pickup_gps_link": s(pickup_gps_link),
        "pickup_1": s(pickup_1), "pickup_2": s(pickup_2),
        "pickup_3": s(pickup_3), "pickup_4": s(pickup_4),
        "pickup_5": s(pickup_5),
        "no_of_guests": (int(no_of_guests) if (no_of_guests or "").strip().isdigit()
                         else None),
        "pickups_sm": s(pickups_sm), "drops_sm": s(drops_sm),
        "drop_address": s(drop_address), "drop_city": s(drop_city),
        "drop_state": s(drop_state), "drop_date": to_date(drop_date),
        "drop_time": s(drop_time), "drop_gps": s(drop_gps),
        "drop_lat": drop_lat_val, "drop_lon": drop_lon_val,
        "drop_manual_address": s(drop_manual_address) or s(drop_address),
        "drop_gps_link": s(drop_gps_link),
        "planned_kms": planned_kms, "planned_hrs": planned_hrs,
        "planned_route_source": planned_source,
        "planned_route_json": planned_route_json,
        "drop_1": s(drop_1), "drop_2": s(drop_2), "drop_3": s(drop_3),
        "drop_4": s(drop_4), "drop_5": s(drop_5),
        "vehicle_type": s(vehicle_type), "package_type": s(package_type),
        "area_code": s(area_code), "reference_code": s(reference_code),
        "ref_no": s(ref_no), "flight_details": s(flight_details),
        "driver_reporting_time": s(driver_reporting_time),
        "done_by_booking": user["user_id"], "step1_time": datetime.now(),
    }
    cols = list(values.keys())
    binds = ", ".join(f":{i + 1}" for i in range(len(cols)))
    cur.execute(
        f"INSERT INTO bookings ({', '.join(cols)}, booking_status, status_reason) "
        f"VALUES ({binds}, '1-Pending', 'Vehicle & Driver Allocation Pending')",
        list(values.values()),
    )
    _save_booking_guest(
        conn, cur, booking_type, booking_id,
        {
            "company_name": company_name,
            "company_id": company_id,
            "guest_name": guest_name,
            "guest_email": guest_email,
            "guest_contact": guest_contact,
            "admin_name": admin_name,
            "admin_contact": admin_contact,
            "admin_email": admin_email,
            "pickup_address": pickup_address,
            "drop_address": drop_address,
            "done_by": user["user_id"],
        },
    )
    audit(conn, user, "Booking Step 1 Submitted", booking_id,
          f"{booking_type} | {guest_name} | pickup {pickup_date} {pickup_time}")
    emit_start(conn, "BOOKING_CREATED", "BOOKING", booking_id,
                    context={"corporate_id": company_id,
                             "booking_type": booking_type, "process_name": "BOOKING",
                             "policy_category": "Booking"})
    notify.notify_step1(conn, user, {
        "booking_id": booking_id, "booking_type": booking_type,
        "company_name": company_name, "guest_name_1": guest_name,
        "guest_email": guest_email, "guest_contact": guest_contact,
        "admin_name": admin_name, "admin_email": admin_email,
        "admin_contact": admin_contact, "pickup_address": pickup_address,
        "pickup_city": pickup_city, "pickup_date": to_date(pickup_date),
        "pickup_time": pickup_time, "drop_address": drop_address,
        "drop_city": drop_city, "vehicle_type": vehicle_type,
        "flight_details": flight_details.strip(),
    })
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=step1-done&notify=1", status_code=303)


@router.post("/{booking_id}/ack-sent")
def booking_ack_sent(request: Request, booking_id: str):
    """Mark the acknowledgement as sent, stamping ack_sent_time on the booking."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_allocate(user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-found",
                                status_code=303)
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(booking_id)):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    now = datetime.now()
    cur.execute(
        "UPDATE bookings SET ack_sent_time=:1 WHERE booking_id=:2 AND ack_sent_time IS NULL",
        (now, booking_id),
    )
    audit(conn, user, "Acknowledgement Sent", booking_id, f"ack_sent_time={now}")
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=ack-sent", status_code=303)


# ---------------------------------------------------------------------------
# Modify / edit after Step 1, 2 or 3 (fields can be corrected any time the
# booking is not cancelled or completed)
# ---------------------------------------------------------------------------
def _to_date(s: str):
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime((s or "").strip(), fmt).date()
        except Exception:
            continue
    return None


def _to_dt(s: str):
    """Parse a timestamp: ISO datetime-local ('2026-08-31T14:30' from the
    calendar picker) or DD-MM-YYYY HH:MM."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S",
                "%d-%m-%Y %H:%M", "%d-%m-%Y %I:%M %p", "%d-%m-%Y %H:%M:%S",
                "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt)
        except Exception:
            continue
    return None


def _s(v):
    return (v or "").strip() or None


def _editable_state(b):
    """A booking may be modified while it is neither cancelled nor completed."""
    status = (b.get("booking_status") or "").strip()
    reason = (b.get("status_reason") or "").strip()
    return not status.startswith("3-") and reason != "Trip Completed"


def _phone_digits(raw):
    d = re.sub(r"\D", "", str(raw or ""))
    if len(d) == 12 and d.startswith("91"):
        d = d[2:]
    return d


def _display_phone(raw):
    """Display phone values without separator artifacts such as '+91 -'."""
    raw_text = str(raw or "").strip()
    digits = re.sub(r"\D", "", raw_text)
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    if len(digits) == 10:
        return digits
    return raw_text.replace(" ", "").replace("-", "")


# Fields reported in modification notifications (column -> readable label)
_MODIFY_LABELS = {
    "booking_type": "Booking Type", "company_name": "Company",
    "company_id": "Company Id", "entity_name": "Entity Name",
    "reference_code": "Reference Code", "ref_no": "Reference No.",
    "guest_name_1": "Guest Name 1", "guest_name_2": "Guest Name 2",
    "guest_name_3": "Guest Name 3", "guest_name_4": "Guest Name 4",
    "guest_name_5": "Guest Name 5", "emp_guest_id": "Emp/Guest ID",
    "guest_email": "Guest Email", "guest_contact": "Guest Contact",
    "admin_name": "Booking SPOC", "admin_email": "Booking SPOC Email",
    "admin_contact": "Booking SPOC Contact",
    "email_received": "Request Received Via",
    "email_sent": "Confirmation Sent Via",
    "request_received_time": "Request Received Time",
    "pickup_address": "Pickup Address", "pickup_city": "Pickup City",
    "pickup_state": "Pickup State", "pickup_date": "Pickup Date",
    "pickup_time": "Pickup Time", "pickup_gps": "Pickup GPS",
    "drop_address": "Drop Address", "drop_city": "Drop City",
    "drop_state": "Drop State", "drop_date": "Drop Date",
    "drop_time": "Drop Time", "drop_gps": "Drop GPS",
    "no_of_guests": "No. of Guests", "pickups_sm": "Pickups",
    "drops_sm": "Drops", "vehicle_type": "Vehicle Type",
    "package_type": "Package Type", "area_code": "Area Code",
    "flight_details": "Flight Details",
    "vendor_name": "Vendor", "vendor_contact": "Vendor Contact",
    "vendor_email": "Vendor Email", "vendor_pkg_type": "Vendor Package",
    "driver_name": "Driver", "driver_contact": "Driver Contact",
    "vehicle_no": "Vehicle No", "driver_reporting_time": "Reporting Time",
    "driver_instructions": "Driver Instructions",
    "special_instructions": "Special Instructions",
}


def _field_changed(col, old, new):
    """Normalized (old, new) pair for change comparison/reporting."""
    if col in ("pickup_date", "drop_date", "request_received_time"):
        fmt = "%d-%m-%Y %H:%M" if col == "request_received_time" else "%d-%m-%Y"
        o = _parse_oracle_dt(old)
        o_s = o.strftime(fmt) if o else ""
        n_s = new.strftime(fmt) if new else ""
        return o_s, n_s
    o_s = str(old or "").strip()
    n_s = str(new if new is not None else "").strip()
    return o_s, n_s


def _diff_changes(old_b, new_vals, cols):
    """List of (label, old, new) for every field that actually changed."""
    changes = []
    for col in cols:
        label = _MODIFY_LABELS.get(col, col.replace("_", " ").title())
        o_s, n_s = _field_changed(col, old_b.get(col), new_vals.get(col))
        if o_s != n_s:
            changes.append((label, o_s or "(blank)", n_s or "(blank)"))
    return changes


@router.get("/{booking_id}/edit")
def booking_edit_page(request: Request, booking_id: str):
    """Modify Booking Details (Step 1 fields) - pre-filled form."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if module_level(user, "Bookings") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    visible = visible_booking_ids(user, cur)
    conn.close()
    if not can_view(visible, str(booking_id)):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    if not _can_modify_booking(user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    if not _editable_state(b):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-editable",
                                status_code=303)
    return templates.TemplateResponse(
        "bookings/edit.html",
        {"request": request, "user": user, "b": b,
         "guest_contact_num": _phone_digits(b.get("guest_contact")),
         "admin_contact_num": _phone_digits(b.get("admin_contact"))},
    )


@router.post("/{booking_id}/edit")
def booking_edit_submit(
    request: Request, booking_id: str,
    booking_type: str = Form(""),
    company_name: str = Form(""),
    company_id: str = Form(""),
    entity_name: str = Form(""),
    reference_code: str = Form(""),
    ref_no: str = Form(""),
    guest_name: str = Form(""),
    guest_name_2: str = Form(""),
    guest_name_3: str = Form(""),
    guest_name_4: str = Form(""),
    guest_name_5: str = Form(""),
    emp_guest_id: str = Form(""),
    guest_email: str = Form(""),
    guest_contact: str = Form(""),
    admin_name: str = Form(""),
    admin_email: str = Form(""),
    admin_contact: str = Form(""),
    email_received: str = Form(""),
    email_sent: str = Form(""),
    request_received_time: str = Form(""),
    pickup_address: str = Form(""),
    pickup_city: str = Form(""),
    pickup_state: str = Form(""),
    pickup_gps: str = Form(""),
    pickup_manual_address: str = Form(""),
    pickup_gps_link: str = Form(""),
    pickup_date: str = Form(""),
    pickup_time: str = Form(""),
    pickup_1: str = Form(""),
    pickup_2: str = Form(""),
    pickup_3: str = Form(""),
    pickup_4: str = Form(""),
    pickup_5: str = Form(""),
    pickup_1_gps: str = Form(""), pickup_2_gps: str = Form(""), pickup_3_gps: str = Form(""),
    pickup_4_gps: str = Form(""), pickup_5_gps: str = Form(""),
    no_of_guests: str = Form(""),
    pickups_sm: str = Form(""),
    drops_sm: str = Form(""),
    drop_address: str = Form(""),
    drop_city: str = Form(""),
    drop_state: str = Form(""),
    drop_gps: str = Form(""),
    drop_manual_address: str = Form(""),
    drop_gps_link: str = Form(""),
    drop_date: str = Form(""),
    drop_time: str = Form(""),
    drop_1: str = Form(""),
    drop_2: str = Form(""),
    drop_3: str = Form(""),
    drop_4: str = Form(""),
    drop_5: str = Form(""),
    drop_1_gps: str = Form(""), drop_2_gps: str = Form(""), drop_3_gps: str = Form(""),
    drop_4_gps: str = Form(""), drop_5_gps: str = Form(""),
    vehicle_type: str = Form(""),
    package_type: str = Form(""),
    area_code: str = Form(""),
    flight_details: str = Form(""),
):
    """Save modified Step 1 details. Allocation (vendor/driver), status and
    timestamps are untouched."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_modify_booking(user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(booking_id)):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    if not _editable_state(b):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-editable",
                                status_code=303)

    planned_stops = _planned_stops(
        pickup_address, pickup_city, pickup_state, "India", pickup_gps,
        [(pickup_1, pickup_1_gps), (pickup_2, pickup_2_gps), (pickup_3, pickup_3_gps), (pickup_4, pickup_4_gps), (pickup_5, pickup_5_gps)],
        drop_address, drop_city, drop_state, "India", drop_gps,
        [(drop_1, drop_1_gps), (drop_2, drop_2_gps), (drop_3, drop_3_gps), (drop_4, drop_4_gps), (drop_5, drop_5_gps)])
    planned_kms, planned_hrs, planned_source, planned_legs = route_estimate_multi(planned_stops)
    planned_route_json = _planned_route_payload(planned_stops, planned_legs)
    values = {
        "booking_type": _s(booking_type), "company_name": _s(company_name),
        "company_id": _s(company_id), "entity_name": _s(entity_name),
        "guest_name_1": _s(guest_name), "guest_name_2": _s(guest_name_2),
        "guest_name_3": _s(guest_name_3), "guest_name_4": _s(guest_name_4),
        "guest_name_5": _s(guest_name_5), "emp_guest_id": _s(emp_guest_id),
        "guest_email": _s(guest_email), "guest_contact": _s(guest_contact),
        "admin_name": _s(admin_name), "admin_email": _s(admin_email),
        "admin_contact": _s(admin_contact),
        "email_received": _s(email_received), "email_sent": _s(email_sent),
        "request_received_time": _to_dt(request_received_time),
        "pickup_address": _s(pickup_address), "pickup_city": _s(pickup_city),
        "pickup_state": _s(pickup_state), "pickup_date": _to_date(pickup_date),
        "pickup_time": _s(pickup_time), "pickup_gps": _s(pickup_gps),
        "pickup_manual_address": _s(pickup_manual_address) or _s(pickup_address),
        "pickup_gps_link": _s(pickup_gps_link),
        "pickup_1": _s(pickup_1), "pickup_2": _s(pickup_2),
        "pickup_3": _s(pickup_3), "pickup_4": _s(pickup_4),
        "pickup_5": _s(pickup_5),
        "no_of_guests": (int(no_of_guests) if (no_of_guests or "").strip().isdigit()
                         else None),
        "pickups_sm": _s(pickups_sm), "drops_sm": _s(drops_sm),
        "drop_address": _s(drop_address), "drop_city": _s(drop_city),
        "drop_state": _s(drop_state), "drop_date": _to_date(drop_date),
        "drop_time": _s(drop_time), "drop_gps": _s(drop_gps),
        "drop_manual_address": _s(drop_manual_address) or _s(drop_address),
        "drop_gps_link": _s(drop_gps_link),
        "planned_kms": planned_kms, "planned_hrs": planned_hrs,
        "planned_route_source": planned_source,
        "planned_route_json": planned_route_json,
        "drop_1": _s(drop_1), "drop_2": _s(drop_2), "drop_3": _s(drop_3),
        "drop_4": _s(drop_4), "drop_5": _s(drop_5),
        "vehicle_type": _s(vehicle_type), "package_type": _s(package_type),
        "area_code": _s(area_code), "reference_code": _s(reference_code),
        "ref_no": _s(ref_no), "flight_details": _s(flight_details),
    }
    sets = ", ".join(f"{c}=:{i + 1}" for i, c in enumerate(values))
    cur.execute(
        f"UPDATE bookings SET {sets} WHERE booking_id=:{len(values) + 1}",
        [*values.values(), booking_id],
    )
    if b.get("driver_name") or b.get("booking_status") == "2-Confirmed":
        _sync_trip_booking_details(conn, dict(b, **values))
    audit(conn, user, "Booking Details Modified (Step 1)", booking_id,
          f"{company_name} | {guest_name} | pickup {pickup_date} {pickup_time}")
    # re-send the changed details to the Guest + Admin
    changes = _diff_changes(b, values, list(values.keys()))
    b_new = dict(b)
    b_new.update(values)
    notify.notify_modification(conn, user, b_new, changes,
                               section="Booking Details (Step 1)")
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=modified",
                            status_code=303)


@router.post("/{booking_id}/modify/vendor")
def modify_vendor(
    request: Request, booking_id: str,
    vendor_name: str = Form(""),
    vendor_contact: str = Form(""),
    vendor_email: str = Form(""),
    vendor_pkg_type: str = Form(""),
):
    """Modify the allocated vendor (Step 2) without changing the status.
    Available even after the booking is confirmed."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_change_vendor(user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(booking_id)):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    if not _editable_state(b):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-editable",
                                status_code=303)
    if not (vendor_name or "").strip():
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=missing-vendor",
                                status_code=303)
    new_vendor = {"vendor_name": vendor_name.strip(),
                  "vendor_contact": vendor_contact.strip(),
                  "vendor_email": vendor_email.strip(),
                  "vendor_pkg_type": vendor_pkg_type.strip()}
    cur.execute(
        "UPDATE bookings SET vendor_name=:1, vendor_contact=:2, "
        "vendor_email=:3, vendor_pkg_type=:4 WHERE booking_id=:5",
        (new_vendor["vendor_name"], new_vendor["vendor_contact"],
         new_vendor["vendor_email"], new_vendor["vendor_pkg_type"], booking_id),
    )
    audit(conn, user, "Vendor Modified (Step 2)", booking_id,
          f"{vendor_name.strip()} | pkg {vendor_pkg_type.strip() or '-'}")
    # re-send the changed details to the Guest + Admin
    changes = _diff_changes(b, new_vendor, list(new_vendor.keys()))
    b_new = dict(b)
    b_new.update(new_vendor)
    notify.notify_modification(conn, user, b_new, changes,
                               section="Vendor (Step 2)")
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=vendor-modified",
                            status_code=303)


@router.post("/{booking_id}/modify/driver")
def modify_driver(
    request: Request, booking_id: str,
    driver_name: str = Form(""),
    driver_contact: str = Form(""),
    vehicle_no: str = Form(""),
    driver_reporting_time: str = Form(""),
    driver_instructions: str = Form(""),
    special_instructions: str = Form(""),
    driver_photo: str = Form(""),
    vehicle_photo: str = Form(""),
):
    """Modify the allocated driver & vehicle (Step 3) without changing the
    status. Also refreshes the live trips row so tracking shows the new
    driver/vehicle."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_change_driver(user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(booking_id)):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    if not _editable_state(b):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-editable",
                                status_code=303)
    if not (driver_name or "").strip() or not (vehicle_no or "").strip():
        conn.close()
        return RedirectResponse(
            url=f"/bookings/{booking_id}?msg=missing-driver-vehicle",
            status_code=303)
    report_time = driver_reporting_time.strip() or \
        _driver_reporting_time(b.get("pickup_time"))
    new_driver = {"driver_name": driver_name.strip(),
                  "driver_contact": driver_contact.strip(),
                  "vehicle_no": vehicle_no.strip(),
                  "driver_reporting_time": report_time,
                  "driver_instructions": driver_instructions.strip() or None,
                  "special_instructions": special_instructions.strip() or None,
                  "driver_photo": driver_photo.strip() or None,
                  "vehicle_photo": vehicle_photo.strip() or None}
    if _is_vendor_portal(user):
        cur.execute(
            "UPDATE bookings SET pending_driver_name=:1, pending_driver_contact=:2, "
            "pending_vehicle_no=:3, pending_driver_reporting_time=:4, "
            "driver_change_status='Pending RentaGO Approval', "
            "driver_change_requested_by=:5, driver_change_requested_on=:6 "
            "WHERE booking_id=:7",
            (new_driver["driver_name"], new_driver["driver_contact"],
             new_driver["vehicle_no"], new_driver["driver_reporting_time"],
             user["user_id"], datetime.now(), booking_id),
        )
        audit(conn, user, "Vendor Driver & Vehicle Change Requested", booking_id,
              f"{new_driver['driver_name']} / {new_driver['vehicle_no']}")
        conn.commit()
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=change-requested",
                                status_code=303)
    cur.execute(
        "UPDATE bookings SET driver_name=:1, driver_contact=:2, vehicle_no=:3, "
        "driver_reporting_time=:4, driver_instructions=:5, "
        "special_instructions=:6, driver_photo=:7, vehicle_photo=:8 "
        "WHERE booking_id=:9",
        (new_driver["driver_name"], new_driver["driver_contact"],
         new_driver["vehicle_no"], new_driver["driver_reporting_time"],
         new_driver["driver_instructions"], new_driver["special_instructions"],
         new_driver["driver_photo"], new_driver["vehicle_photo"], booking_id),
    )
    cur.execute(
        "UPDATE trips SET driver_name=:1, driver_mobile=:2, vehicle_no=:3, "
        "driver_reporting_time=:4 WHERE booking_id=:5",
        (new_driver["driver_name"], new_driver["driver_contact"],
         new_driver["vehicle_no"], new_driver["driver_reporting_time"],
         booking_id),
    )
    audit(conn, user, "Driver & Vehicle Modified (Step 3)", booking_id,
          f"{driver_name.strip()} / {vehicle_no.strip()}")
    # re-send the changed details to the Guest + Admin (+ the new driver)
    changes = _diff_changes(b, new_driver,
                            ("driver_name", "driver_contact", "vehicle_no",
                             "driver_reporting_time", "driver_instructions",
                             "special_instructions"))
    b_new = dict(b)
    b_new.update(new_driver)
    notify.notify_modification(conn, user, b_new, changes,
                               section="Driver & Vehicle (Step 3)",
                               notify_driver=True)
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=driver-modified",
                            status_code=303)


@router.post("/{booking_id}/approve-driver-change")
def approve_driver_change(request: Request, booking_id: str):
    """Approve a vendor-submitted vehicle/driver change from RentaGO Operations."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if (user.get("role") or "").strip().lower() == "driver":
        return RedirectResponse(url="/mobile/driver", status_code=303)
    if (user.get("role") or "").strip().lower() in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}:
        return RedirectResponse(url="/dashboards/vendor", status_code=303)
    if _participant_mobile_only(request, user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=mobile-only",
                                status_code=303)
    if not _can_change_vendor(user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b or (b.get("driver_change_status") or "").strip() != "Pending RentaGO Approval":
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=no-change-request",
                                status_code=303)
    cur.execute(
        "UPDATE bookings SET driver_name=pending_driver_name, "
        "driver_contact=pending_driver_contact, vehicle_no=pending_vehicle_no, "
        "driver_reporting_time=pending_driver_reporting_time, "
        "driver_change_status='Approved', pending_driver_name=NULL, "
        "pending_driver_contact=NULL, pending_vehicle_no=NULL, "
        "pending_driver_reporting_time=NULL WHERE booking_id=:1",
        (booking_id,),
    )
    cur.execute(
        "UPDATE trips SET driver_name=(SELECT driver_name FROM bookings WHERE booking_id=:1), "
        "driver_mobile=(SELECT driver_contact FROM bookings WHERE booking_id=:2), "
        "vehicle_no=(SELECT vehicle_no FROM bookings WHERE booking_id=:3), "
        "driver_reporting_time=(SELECT driver_reporting_time FROM bookings WHERE booking_id=:4) "
        "WHERE booking_id=:5",
        (booking_id, booking_id, booking_id, booking_id, booking_id),
    )
    audit(conn, user, "Vendor Driver & Vehicle Change Approved", booking_id, "")
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=change-approved",
                            status_code=303)


@router.post("/{booking_id}/feedback")
def submit_feedback(request: Request, booking_id: str,
                    rating: str = Form(""), feedback: str = Form(""),
                    went_well: list[str] = Form([]), improvements: list[str] = Form([]),
                    safety_status: str = Form(""), safety_issues: list[str] = Form([])):
    """Allow the guest to submit one rating/comment after trip completion."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    role = (user.get("role") or "").strip().lower()
    if role != "guest":
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b or not can_view(visible_booking_ids(user, cur), str(booking_id)):
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    if (b.get("status_reason") or "").strip() != "Trip Completed":
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=feedback-not-ready", status_code=303)
    cur.execute("SELECT guest_rating, feedback_submitted_on, actual_end_dt, drop_end_time "
                "FROM trips WHERE booking_id=:1 ORDER BY trip_id DESC FETCH FIRST 1 ROWS ONLY",
                (booking_id,))
    submitted_row = cur.fetchone()
    previous_rating = None
    if submitted_row and str(submitted_row[0] or "").strip():
        try:
            previous_rating = int(submitted_row[0])
        except (TypeError, ValueError):
            previous_rating = None
    submitted_on = _parse_oracle_dt(submitted_row[1]) if submitted_row else None
    end_dt = _parse_oracle_dt(submitted_row[2]) if submitted_row else None
    if end_dt is None and submitted_row:
        end_dt = _parse_oracle_dt(submitted_row[3])
    if previous_rating is None and end_dt and datetime.now() > end_dt + timedelta(hours=72):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=feedback-closed", status_code=303)
    within_edit_window = not submitted_on or datetime.now() <= submitted_on + timedelta(hours=24)
    if previous_rating is not None and (previous_rating > 3 or not within_edit_window):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=feedback-locked", status_code=303)
    try:
        score = int(rating)
    except (TypeError, ValueError):
        score = 0
    if score not in range(1, 6):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=feedback-invalid", status_code=303)
    comment = (feedback or "").strip()[:2000]
    well = ", ".join(went_well)[:2000]
    improve = ", ".join(improvements)[:2000]
    allowed_safety = {"Yes", "Some concern", "Safety issue"}
    if safety_status not in allowed_safety:
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=feedback-invalid", status_code=303)
    issues = ", ".join(safety_issues)[:2000]
    priority = None
    if safety_status == "Safety issue":
        priority = "P0" if any(x in issues for x in ("Emergency", "Harassment", "Vehicle safety issue")) else "P1"
    feedback_owner_group = owner_group(went_well, improvements, safety_status, safety_issues)
    cur.execute(
        "UPDATE trips SET guest_rating=:1, guest_feedback=:2, feedback_went_well=:3, "
        "feedback_improvements=:4, safety_status=:5, safety_issues=:6, "
        "incident_priority=:7, incident_status=:8, feedback_owner_group=:9, "
        "feedback_submitted_on=:10 WHERE booking_id=:11",
        (score, comment or None, well or None, improve or None, safety_status,
         issues or None, priority, "Open" if priority else None, feedback_owner_group,
         datetime.now(), booking_id),
    )
    audit(conn, user, "Guest Feedback Submitted", booking_id, f"rating={score}")
    emit_start(conn, "FEEDBACK_SUBMITTED", "BOOKING", booking_id, department="Customer Service",
               context={"rating": score, "safety_status": safety_status,
                        "incident_priority": priority or "P2", "policy_category": "Customer Service"})
    if priority:
        notify.notify_safety_incident(conn, user, b, priority, issues)
        emit_start(conn, "SAFETY_INCIDENT", "BOOKING", booking_id, department="Safety",
                   context={"incident_priority": priority, "safety_status": safety_status,
                            "policy_category": "Safety"})
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=feedback-saved", status_code=303)


@router.post("/{booking_id}/share-live-tracking/{who}")
def share_live_tracking(request: Request, booking_id: str, who: str):
    """Let the assigned guest or driver share tracking with RentaGO."""
    user = current_user(request)
    role = (user or {}).get("role", "").strip().lower()
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not is_mobile_request(request) or who not in ("guest", "driver"):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=mobile-only", status_code=303)
    if (who == "guest" and role != "guest") or (who == "driver" and role != "driver"):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b or not can_view(visible_booking_ids(user, cur), str(booking_id)):
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    if who == "driver" and not _driver_matches_booking(user, b):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-driver-action", status_code=303)
    from ..tracking import ensure_track_token
    token = ensure_track_token(cur, booking_id)
    # Use the host currently used by the participant. This avoids stale
    # Cloudflare quick-tunnel URLs saved in the settings table.
    base = str(request.base_url).rstrip("/")
    link = f"{base}/track/{booking_id}/{who}/{token}"
    notify.notify_tracking_shared(conn, user, b, who, link)
    audit(conn, user, f"{who.title()} Shared Live Tracking", booking_id, link)
    conn.commit()
    conn.close()
    # The participant must open the private tracking page so the browser can
    # request GPS permission and begin saving positions.
    return RedirectResponse(
        url=f"/mobile/{who}?msg=tracking-shared&tracking_link={quote(link, safe='')}",
        status_code=303)


@router.post("/{booking_id}/sos")
def trigger_sos(request: Request, booking_id: str):
    """Trigger an emergency alert for a Guest or Corporate Admin mobile user."""
    user = current_user(request)
    role = (user or {}).get("role", "").strip().lower()
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not is_mobile_request(request) or (role != "guest" and not _is_corporate(user)):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=mobile-only", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b or not can_view(visible_booking_ids(user, cur), str(booking_id)):
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    notify.notify_sos(conn, user, b)
    emit_start(conn, "SOS_EMERGENCY", "BOOKING", booking_id, department="Safety",
               context={"incident_priority": "P0", "policy_category": "Safety"})
    audit(conn, user, "SOS Emergency Triggered", booking_id, "red trigger sent")
    conn.commit()
    conn.close()
    if role == "guest":
        return RedirectResponse(url="/mobile/guest?msg=sos-sent", status_code=303)
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=sos-sent", status_code=303)


@router.get("/{booking_id}/gps-trail")
def gps_trail(request: Request, booking_id: str, who: str = ""):
    """Full GPS trail of an ongoing/completed trip - every 30-second capture
    from the tracking database, kept for future reference and billing."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if _participant_mobile_only(request, user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=mobile-only",
                                status_code=303)
    if module_level(user, "Bookings") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(booking_id)):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    cur.execute(
        "SELECT log_id, who, lat, lon, distance_m, location_sync, location_address, captured_dt "
        "FROM gps_log WHERE booking_id=:1 ORDER BY captured_dt, log_id",
        (booking_id,),
    )
    rows = cur.fetchall()
    conn.close()

    captures = []
    driver_pts, guest_pts = [], []
    for r in rows:
        dt = _parse_oracle_dt(r[7])
        captures.append({
            "log_id": r[0], "who": str(r[1] or "").strip(), "lat": r[2],
            "lon": r[3], "distance_m": r[4],
            "location_sync": str(r[5] or "").strip() or None,
            "location_address": r[6] or "",
            "captured": dt.strftime("%d-%m-%Y %I:%M:%S %p") if dt else "-",
            "dt": dt,
        })
        try:
            pt = (float(r[2]), float(r[3]))
            if captures[-1]["who"] == "driver":
                driver_pts.append(pt)
            elif captures[-1]["who"] == "guest":
                guest_pts.append(pt)
        except Exception:
            pass

    def path_km(pts):
        total = 0.0
        for i in range(1, len(pts)):
            total += distance_meters(pts[i - 1][0], pts[i - 1][1],
                                     pts[i][0], pts[i][1])
        return round(total / 1000.0, 2)

    reds = sum(1 for c in captures if c["location_sync"] == "RED FLAG")
    summary = {
        "total": len(captures),
        "driver": sum(1 for c in captures if c["who"] == "driver"),
        "guest": sum(1 for c in captures if c["who"] == "guest"),
        "driver_km": path_km(driver_pts),
        "guest_km": path_km(guest_pts),
        "red_flags": reds,
        "first": captures[0]["captured"] if captures else "-",
        "last": captures[-1]["captured"] if captures else "-",
    }
    map_source = [c for c in captures if not who or c["who"] == who]
    map_points = [{"lat": float(c["lat"]), "lon": float(c["lon"]), "who": c["who"],
                  "address": c["location_address"], "captured": c["captured"]}
                  for c in map_source]
    try:
        planned_raw = b.get("planned_route_json") or "{}"
        if hasattr(planned_raw, "read"):
            planned_raw = planned_raw.read()
        planned_payload = json.loads(planned_raw or "{}")
    except (TypeError, ValueError):
        planned_payload = {}
    planned_map_points = [
        {"lat": float(stop["lat"]), "lon": float(stop["lon"]), "label": stop.get("label", "Stop"),
         "address": stop.get("address", "")}
        for stop in planned_payload.get("stops", [])
        if stop.get("lat") is not None and stop.get("lon") is not None
    ]
    remaining_km = None
    remaining_hours = None
    remaining_source = ""
    final_stop = planned_map_points[-1] if planned_map_points else None
    if final_stop:
        try:
            if driver_pts:
                route = location_service.route(driver_pts[-1], (final_stop["lat"], final_stop["lon"]))
                remaining_km = route.distance_km
                remaining_hours = route.duration_hours
                remaining_source = "Latest driver GPS"
            elif b.get("planned_kms") is not None:
                remaining_km = float(b.get("planned_kms"))
                remaining_hours = float(b.get("planned_hrs") or 0)
                remaining_source = "Planned route - waiting for driver GPS"
        except Exception:
            remaining_km, remaining_hours = None, None
    return templates.TemplateResponse(
        "bookings/gps_trail.html",
        {"request": request, "user": user, "b": b, "captures": captures,
          "summary": summary, "map_points": map_points, "planned_map_points": planned_map_points,
          "remaining_km": remaining_km, "remaining_hours": remaining_hours,
          "remaining_source": remaining_source,
           "show_planned_route": _is_rentago_override(user), "from_mobile": request.query_params.get("from") == "mobile", "trail_who": who},
    )


@router.get("/{booking_id}/gps-trail/csv")
def gps_trail_csv(request: Request, booking_id: str):
    """Download the GPS trail as CSV (billing record for the guest/client)."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if _participant_mobile_only(request, user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=mobile-only",
                                status_code=303)
    if module_level(user, "Bookings") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(booking_id)):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    cur.execute(
        "SELECT log_id, who, lat, lon, distance_m, location_sync, location_address, captured_dt "
        "FROM gps_log WHERE booking_id=:1 ORDER BY captured_dt, log_id",
        (booking_id,),
    )
    rows = cur.fetchall()
    conn.close()
    lines = ["Capture ID,Who,Latitude,Longitude,Address,Distance to other party (m),"
             "Sync status,Captured at"]
    for r in rows:
        dt = _parse_oracle_dt(r[7])
        lines.append(",".join([
            str(r[0] or ""), str(r[1] or ""),
            str(r[2] or ""), str(r[3] or ""),
             str(r[4] or ""), str(r[5] or ""), str(r[6] or ""),
             dt.strftime("%d-%m-%Y %I:%M:%S %p") if dt else "",
        ]))
    csv_text = "\n".join(lines) + "\n"
    return Response(
        content=csv_text, media_type="text/csv",
        headers={"Content-Disposition":
                 f'attachment; filename="{booking_id}-gps-trail.csv"'})


@router.get("/{booking_id}")
def booking_detail(request: Request, booking_id: str):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if (user.get("role") or "").strip().lower() == "driver":
        return RedirectResponse(url="/mobile/driver", status_code=303)
    if (user.get("role") or "").strip().lower() in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}:
        return RedirectResponse(url="/dashboards/vendor", status_code=303)
    if _participant_mobile_only(request, user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=mobile-only",
                                status_code=303)
    if module_level(user, "Bookings") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    # One batched round-trip (a single sqlplus spawn on the fallback driver)
    # for the booking row, its invoice, trip, step1 timestamp and notifications.
    blocks = multi_fetch(conn, [
        ("SELECT * FROM bookings WHERE booking_id=:1", (booking_id,)),
        ("SELECT invoice_id FROM invoices WHERE booking_id=:1 "
         "ORDER BY invoice_id DESC FETCH FIRST 1 ROWS ONLY", (booking_id,)),
        ("SELECT * FROM trips WHERE booking_id=:1", (booking_id,)),
        ("SELECT TO_CHAR(step1_time, 'YYYY-MM-DD HH24:MI:SS') FROM bookings "
         "WHERE booking_id=:1", (booking_id,)),
        ("SELECT notification_id, event, channel, recipient_name, subject, link, "
         "status FROM notifications WHERE booking_id=:1 "
         "ORDER BY notification_id DESC FETCH FIRST 20 ROWS ONLY", (booking_id,)),
        ("SELECT COUNT(*), NVL(SUM(CASE WHEN location_sync='RED FLAG' THEN 1 ELSE 0 END),0) FROM gps_log WHERE booking_id=:1", (booking_id,)),
    ])
    b_headers, b_rows = blocks[0]
    if not b_rows:
        conn.close()
        return templates.TemplateResponse("bookings/not_found.html", {"request": request, "user": user})
    data = dict(zip(b_headers, b_rows[0]))
    if (user.get("tenant_id") and (user.get("role") or "").strip().lower() != "super admin"
            and str(data.get("tenant_id") or "") != str(user["tenant_id"])):
        conn.close()
        return templates.TemplateResponse("bookings/not_found.html", {"request": request, "user": user})
    visible = visible_booking_ids(user, conn.cursor())
    if not can_view(visible, str(booking_id)):
        conn.close()
        return templates.TemplateResponse("bookings/not_found.html", {"request": request, "user": user})
    show_vendor_details = (user.get("role") or "").strip().lower() not in {
        "guest", *CORPORATE_PORTAL_ROLES,
    }
    view_data = dict(data)
    if not show_vendor_details:
        for key in ("vendor_name", "vendor_contact", "vendor_email", "vendor_pkg_type",
                    "vendor_deadline"):
            view_data[key] = None
    # Backfill route planning for older multi-stop bookings created before the
    # ordered planned-route payload was introduced.
    if not data.get("planned_route_json") and any(data.get(f"pickup_{i}") or data.get(f"drop_{i}") for i in range(1, 6)):
        legacy_stops = _planned_stops(
            data.get("pickup_address"), data.get("pickup_city"), data.get("pickup_state"), "India", data.get("pickup_gps"),
            [(data.get(f"pickup_{i}"), "") for i in range(1, 6)],
            data.get("drop_address"), data.get("drop_city"), data.get("drop_state"), "India", data.get("drop_gps"),
            [(data.get(f"drop_{i}"), "") for i in range(1, 6)])
        legacy_km, legacy_hrs, legacy_source, legacy_legs = route_estimate_multi(legacy_stops)
        legacy_json = _planned_route_payload(legacy_stops, legacy_legs)
        conn.cursor().execute("UPDATE bookings SET planned_kms=:1, planned_hrs=:2, planned_route_source=:3, planned_route_json=:4 WHERE booking_id=:5",
                              (legacy_km, legacy_hrs, legacy_source, legacy_json, booking_id))
        conn.commit()
        data.update({"planned_kms": legacy_km, "planned_hrs": legacy_hrs,
                     "planned_route_source": legacy_source, "planned_route_json": legacy_json})
        view_data.update(data)
    invoice_id = blocks[1][1][0][0] if blocks[1][1] else None
    trip = None
    t_headers, t_rows = blocks[2]
    if t_rows:
        trip = dict(zip(t_headers, t_rows[0]))
    entry_s = blocks[3][1][0][0] if blocks[3][1] else ""
    entry_s = str(entry_s or "").strip()
    # ---- SLA: request received -> step1 capture -> acknowledgement ----
    # Values come from the DB as Oracle timestamp strings
    # ('31-AUG-26 01.48.30.000000 PM') - _parse_oracle_dt handles those.
    recv_dt = _parse_oracle_dt(data.get("request_received_time"))
    if recv_dt is None:
        recv_dt = datetime.now()  # no received time recorded -> assume now
    ack_dt = _parse_oracle_dt(data.get("ack_sent_time"))
    step1_dt = None
    if entry_s:
        try:
            step1_dt = datetime.strptime(entry_s, "%Y-%m-%d %H:%M:%S")
        except Exception:
            step1_dt = None

    ACK_SLA_MINUTES = 15
    capture_mins = round((step1_dt - recv_dt).total_seconds() / 60, 1) \
        if step1_dt and recv_dt else None
    ack_mins = round((ack_dt - recv_dt).total_seconds() / 60, 1) \
        if ack_dt and recv_dt else None
    # Breached if ack not sent within target, or (pending ack and now - recv > target)
    if ack_dt and recv_dt:
        ack_breached = (ack_dt - recv_dt).total_seconds() > ACK_SLA_MINUTES * 60
    elif recv_dt:
        ack_breached = (datetime.now() - recv_dt).total_seconds() > ACK_SLA_MINUTES * 60
    else:
        ack_breached = None
    ack_pending = ack_dt is None
    feedback_dt = _parse_oracle_dt(data.get("feedback_submitted_on"))
    try:
        feedback_rating = int(data.get("guest_rating")) if data.get("guest_rating") is not None else None
    except (TypeError, ValueError):
        feedback_rating = None
    feedback_editable = (feedback_rating is None or
                         (feedback_rating <= 3 and
                          (not feedback_dt or datetime.now() <= feedback_dt + timedelta(hours=24))))
    end_dt = _parse_oracle_dt(trip.get("actual_end_dt")) if trip else None
    if end_dt is None and trip:
        end_dt = _parse_oracle_dt(trip.get("drop_end_time"))
    feedback_submission_open = not end_dt or datetime.now() <= end_dt + timedelta(hours=72)

    sla_info = {
        "recv_dt": recv_dt, "ack_dt": ack_dt, "step1_dt": step1_dt,
        "capture_mins": capture_mins, "ack_mins": ack_mins,
        "ack_breached": ack_breached, "target": ACK_SLA_MINUTES,
        "ack_pending": ack_pending,
    }
    # -----------------------------------------------------------

    alloc_elig = _allocation_eligibility(conn.cursor(), data, entry_s=entry_s)
    n_headers, n_rows = blocks[4]
    notes = [dict(zip(("notification_id", "event", "channel", "recipient_name",
                       "subject", "link", "status"), r)) for r in n_rows
             if can_see_notification(user, r[1])]

    gps_headers, gps_rows = blocks[5]
    # gps_rows is a list of row tuples; this query returns exactly 1 row:
    #   SELECT COUNT(*), NVL(SUM(CASE WHEN location_sync='RED FLAG' THEN 1 ELSE 0 END),0) ...
    if gps_rows and len(gps_rows) > 0:
        row = gps_rows[0]  # tuple (count, red_flag_count)
        gps_count = int(row[0]) if row[0] is not None else 0
        gps_redflags = int(row[1]) if len(row) > 1 and row[1] is not None else 0
    else:
        gps_count = 0
        gps_redflags = 0

    try:
        planned_raw = data.get("planned_route_json") or "{}"
        if hasattr(planned_raw, "read"):
            planned_raw = planned_raw.read()
        planned_route = json.loads(planned_raw or "{}")
    except (TypeError, ValueError):
        planned_route = {}
    conn.close()
    return templates.TemplateResponse(
        "bookings/detail.html",
         {"request": request, "user": user, "b": view_data, "invoice_id": invoice_id,
          "trip": trip, "can_allocate": _can_allocate(user),
          "planned_route": planned_route,
          "can_cancel": _can_modify_booking(user) and not (
             (data.get("booking_status") or "").startswith("3-")
             or (data.get("status_reason") or "").strip() == "Trip Completed"
         ),
          "can_edit": _can_modify_booking(user) and _editable_state(data),
          "can_change_vendor": _can_change_vendor(user),
          "can_change_driver": _can_change_driver(user),
          "can_guest_trip_action": _can_guest_trip_action(user),
          "can_driver_trip_action": _can_driver_trip_action(user, data),
          "can_operate_trip": (_can_guest_trip_action(user)
                               or _can_driver_trip_action(user, data)),
           "can_feedback": ((user.get("role") or "").strip().lower() == "guest"
                            and (data.get("status_reason") or "").strip() == "Trip Completed"
                            and feedback_editable and feedback_submission_open),
           "feedback_locked": ((user.get("role") or "").strip().lower() == "guest"
                                and feedback_rating is not None and not feedback_editable),
           "feedback_closed": ((user.get("role") or "").strip().lower() == "guest"
                               and feedback_rating is None and not feedback_submission_open),
          "can_share_tracking": ((user.get("role") or "").strip().lower() in {"guest", "driver"}
                                 and is_mobile_request(request)),
          "can_sos": ((user.get("role") or "").strip().lower() == "guest"
                      or _is_corporate(user)) and is_mobile_request(request),
          "show_vendor_details": show_vendor_details,
           "show_planned_route": _is_rentago_override(user),
           "show_driver_profile": ((user.get("role") or "").strip().lower() == "guest"
                                   or _is_corporate(user) or _is_rentago_override(user)),
          "show_rentago_triggers": _is_rentago_override(user),
          "guest_contact_display": _display_phone(data.get("guest_contact")),
          "admin_contact_display": _display_phone(data.get("admin_contact")),
         "cancellation_policy": [
             {"code": c, "desc": d, "charge": ch}
             for c, (d, ch) in sorted(CANCELLATION_POLICY.items())
         ],
          "alloc_elig": alloc_elig, "notes": notes,
          "notify_notes": [n for n in notes if str(n.get("event") or "").lower().startswith("step")], "sla_info": sla_info,
          "gps_count": gps_count, "gps_redflags": gps_redflags},
    )


@router.post("/{booking_id}/trip/start-driver")
@router.post("/{booking_id}/start-trip", include_in_schema=False)
def start_trip(request: Request, booking_id: str,
               pickup_start_km: str = Form("")):
    """Start the trip (Driver action). Mirrors VBA StartTripDriver.

    Precondition: the trip may only be started by the driver after the guest has
    started it (status_reason == "Guest Trip Started - Awaiting Driver Confirmation").
    Creates the trips row and moves the booking to 'Trip In Progress'.
    """
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if _participant_mobile_only(request, user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=mobile-only",
                                status_code=303)

    conn = get_connection()
    cur = conn.cursor()
    row = _get_booking(cur, booking_id)
    if not row:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    b = row

    if not _is_rentago_override(user) and not _rentago_operator_present(cur):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=rentago-presence-required", status_code=303)

    if not _can_driver_trip_action(user, b):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-driver-action",
                                status_code=303)

    reason = (b.get("status_reason") or "").strip()
    if reason == "Trip In Progress":
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=in-progress", status_code=303)
    if reason != "Guest Trip Started - Awaiting Driver Confirmation":
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=guest-must-start", status_code=303)
    try:
        start_km = float(pickup_start_km)
        if start_km < 0:
            raise ValueError
    except (TypeError, ValueError):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=pickup-odometer-required", status_code=303)

    trip_id = _next_trip_id(conn)
    start_now = datetime.now()
    guest = (b.get("guest_name_1") or b.get("guest_name") or "")
    cur.execute(
        """INSERT INTO trips (
            trip_id, tenant_id, booking_id, guest_name, pickup_date, pickup_address,
            drop_address, driver_name, vehicle_no, booking_status, trip_status,
            driver_mobile, driver_reporting_time, pickup_start_time, actual_start_dt,
            pickup_start_km,
            google_maps_link
        ) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,'In Progress','In Progress',:10,:11,:12,:13,:14,:15)""",
        (
            trip_id, b.get("tenant_id") or "TEN-RENTA-GO", booking_id, guest, b.get("pickup_date"), b.get("pickup_address"),
            b.get("drop_address"), b.get("driver_name"), b.get("vehicle_no"),
            b.get("driver_contact"), b.get("driver_reporting_time") or "",
            start_now.strftime("%I:%M %p"), start_now, start_km, "",
        ),
    )
    cur.execute(
        "UPDATE bookings SET booking_status='2-Confirmed', status_reason='Trip In Progress', "
        "done_by_driver=:1, step1_time=:2 WHERE booking_id=:3",
        (user["user_id"], start_now, booking_id),
    )
    audit(conn, user, "Trip Started (Driver)", booking_id, f"Trip {trip_id} In Progress")
    complete_for_entity(conn, "BOOKING", booking_id, ("TRIP_STARTED_GUEST",), "Driver confirmed trip start")
    emit_start(conn, "TRIP_STARTED_DRIVER", "BOOKING", booking_id,
               context={"booking_type": b.get("booking_type"), "corporate_id": b.get("company_id"), "policy_category": "Booking"})
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=trip-started", status_code=303)


@router.post("/{booking_id}/trip/start-guest")
def start_trip_guest(request: Request, booking_id: str):
    """Start the trip (Guest/Admin action). Mirrors VBA StartTripGuest.

    Preconditions: trip not already started; only after booking is Confirmed
    (booking_status == '2-Confirmed'). Sets status_reason to
    'Guest Trip Started - Awaiting Driver Confirmation'.
    """
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if _participant_mobile_only(request, user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=mobile-only",
                                status_code=303)

    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    if not _is_rentago_override(user) and not _rentago_operator_present(cur):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=rentago-presence-required", status_code=303)
    if not _can_guest_trip_action(user):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-guest-action",
                                status_code=303)

    reason = (b.get("status_reason") or "").strip()
    if reason in (
        "Guest Trip Started - Awaiting Driver Confirmation",
        "Trip In Progress",
        "Guest Trip Ended - Awaiting Driver Confirmation",
        "Trip Completed",
    ):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=already-in-trip", status_code=303)
    if (b.get("booking_status") or "").strip() != "2-Confirmed":
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-confirmed", status_code=303)

    cur.execute(
        "UPDATE bookings SET booking_status='2-Confirmed', guest_end_trigger='TRIGGERED', "
        "status_reason='Guest Trip Started - Awaiting Driver Confirmation', "
        "done_by_booking=:1, step1_time=:2 WHERE booking_id=:3",
        (user["user_id"], datetime.now(), booking_id),
    )
    audit(conn, user, "Trip Started (Guest)", booking_id, "")
    complete_for_entity(conn, "BOOKING", booking_id, ("CUSTOMER_CONFIRMATION_REQUIRED",), "Customer confirmed booking by starting trip")
    emit_start(conn, "TRIP_STARTED_GUEST", "BOOKING", booking_id,
               context={"booking_type": b.get("booking_type"), "corporate_id": b.get("company_id"), "policy_category": "Booking"})
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=guest-started", status_code=303)


@router.post("/{booking_id}/trip/end-guest")
def end_trip_guest(request: Request, booking_id: str):
    """End the trip (Guest/Admin action). Mirrors VBA EndTripGuest.

    Precondition: trip must be 'Trip In Progress'. Sets status_reason to
    'Guest Trip Ended - Awaiting Driver Confirmation'.
    """
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if _participant_mobile_only(request, user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=mobile-only",
                                status_code=303)

    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    if not _is_rentago_override(user) and not _rentago_operator_present(cur):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=rentago-presence-required", status_code=303)
    if not _can_guest_trip_action(user):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-guest-action",
                                status_code=303)

    reason = (b.get("status_reason") or "").strip()
    if reason == "Guest Trip Ended - Awaiting Driver Confirmation":
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=guest-already-ended", status_code=303)
    if reason == "Trip Completed":
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=completed", status_code=303)
    if reason != "Trip In Progress":
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-in-progress", status_code=303)

    cur.execute(
        "UPDATE bookings SET booking_status='2-Confirmed', "
        "status_reason='Guest Trip Ended - Awaiting Driver Confirmation', "
        "done_by_booking=:1 WHERE booking_id=:2",
        (user["user_id"], booking_id),
    )
    audit(conn, user, "Trip Ended (Guest)", booking_id, "")
    notify.notify_trip_trigger(conn, user, b, "Guest/Admin End Trip")
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=guest-ended", status_code=303)


@router.post("/{booking_id}/trip/end-driver")
def end_trip_driver(request: Request, booking_id: str,
                    drop_end_km: str = Form("")):
    """End the trip (Driver action). Mirrors VBA EndTripDriver.

    Precondition: the driver may only end after the guest has ended
    (status_reason == 'Guest Trip Ended - Awaiting Driver Confirmation').
    Marks the trips row 'Trip Completed' and completes the booking.
    """
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if _participant_mobile_only(request, user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=mobile-only",
                                status_code=303)

    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    if not _is_rentago_override(user) and not _rentago_operator_present(cur):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=rentago-presence-required", status_code=303)
    if not _can_driver_trip_action(user, b):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-driver-action",
                                status_code=303)

    reason = (b.get("status_reason") or "").strip()
    if reason == "Trip Completed":
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=completed", status_code=303)
    if reason != "Guest Trip Ended - Awaiting Driver Confirmation":
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=guest-must-end", status_code=303)

    try:
        end_km = float(drop_end_km)
        if end_km < 0:
            raise ValueError
    except (TypeError, ValueError):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=drop-odometer-required", status_code=303)

    now = datetime.now()
    trip_row = _find_trip_row(cur, booking_id)
    if trip_row is not None:
        cur.execute("UPDATE trips SET drop_end_km=:1 WHERE booking_id=:2",
                    (end_km, booking_id))
        trip_row = _find_trip_row(cur, booking_id)
        _save_trip_actuals(conn, b, trip_row, now)
    cur.execute(
        "UPDATE trips SET booking_status='Trip Completed', trip_status='Trip Completed', "
        "drop_end_time=:1 WHERE booking_id=:2",
        (now.strftime("%I:%M %p"), booking_id),
    )
    cur.execute(
        "UPDATE bookings SET booking_status='2-Confirmed', status_reason='Trip Completed', "
        "driver_end_trigger='TRIGGERED', feedback_trigger='FEEDBACK PENDING', "
        "done_by_driver=:1 WHERE booking_id=:2",
        (user["user_id"], booking_id),
    )
    invoice_id = _generate_provisional_invoice(conn, b, now)
    _ensure_vendor_invoice(conn, b, now)
    audit(conn, user, "Trip Completed (Driver)", booking_id,
          f"Provisional invoice {invoice_id or '-'} generated")
    complete_for_entity(conn, "BOOKING", booking_id, ("TRIP_STARTED_DRIVER",), "Driver completed trip")
    emit_start(conn, "TRIP_COMPLETED", "BOOKING", booking_id,
               context={"booking_type": b.get("booking_type"), "corporate_id": b.get("company_id"), "policy_category": "Booking"})
    notify.notify_trip_trigger(conn, user, b, "Driver End Trip / Feedback Pending")
    conn.commit()
    conn.close()
    target = f"/bookings/{booking_id}?msg=trip-completed"
    if invoice_id:
        target += f"&inv={invoice_id}"
    return RedirectResponse(url=target, status_code=303)


@router.post("/{booking_id}/location/{who}")
def save_live_location(request: Request, booking_id: str, who: str,
                       live_location: str = Form("")):
    """Save a live location link for a trip.

    Mirrors VBA SaveDriverLiveLocation / SaveGuestLocation: stores the Google
    Maps live-location link on the booking and recomputes LOCATION_SYNC.
    `who` is either 'driver' or 'guest'.

    Tracking windows (relative to pickup time):
      - driver: open 2 hours prior to pickup, through the end of the trip
      - guest:  open 15 minutes prior to pickup, through the end of the trip
    Once the trip ends, both tracked parties are automatically deactivated
    (the booking's live fields are cleared in _save_trip_actuals) and updates
    are rejected.
    """
    if who not in ("driver", "guest"):
        return RedirectResponse(url="/bookings", status_code=303)
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)

    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(booking_id)):
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)

    reason = (b.get("status_reason") or "").strip()
    active = reason in (
        "Booking Confirmed - Driver & Vehicle Allocated",
        "Guest Trip Started - Awaiting Driver Confirmation",
        "Trip In Progress",
        "Guest Trip Ended - Awaiting Driver Confirmation",
    )
    if not active:
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=location-not-active",
                                status_code=303)

    if not _tracking_window_open(b, who):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=location-not-active",
                                status_code=303)

    link = (live_location or "").strip()
    if not link or "http" not in link.lower():
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=location-link-invalid",
                                status_code=303)

    column = "driver_live_location" if who == "driver" else "guest_live_location"
    cur.execute(f"UPDATE bookings SET {column}=:1 WHERE booking_id=:2",
                (link, booking_id))
    driver_link = link if who == "driver" else (b.get("driver_live_location") or "")
    guest_link = link if who == "guest" else (b.get("guest_live_location") or "")
    sync = sync_status_text(driver_link, guest_link)
    cur.execute(
        "UPDATE bookings SET location_sync=:1 WHERE booking_id=:2",
        (sync, booking_id),
    )
    if sync == "RED FLAG":
        report = gps_report(driver_link, guest_link, sync)
        notify.notify_red_flag(conn, user, dict(b, driver_live_location=driver_link,
                                                guest_live_location=guest_link), report)
    audit(conn, user, f"Live Location Saved ({who.title()})", booking_id,
          f"sync={sync}")
    conn.commit()
    conn.close()
    msg = "driver-location-saved" if who == "driver" else "guest-location-saved"
    return RedirectResponse(url=f"/bookings/{booking_id}?msg={msg}", status_code=303)


@router.post("/{booking_id}/request-driver-location")
def request_driver_location(request: Request, booking_id: str):
    """Queue a WhatsApp to the driver with live-location sharing steps
    (SOP 8.2 - Request Driver Location)."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_allocate(user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    if not (b.get("driver_contact") or "").strip():
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=no-driver-contact",
                                status_code=303)
    notify.request_driver_location(conn, user, b)
    audit(conn, user, "Driver Location Requested", booking_id, "")
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=location-requested",
                            status_code=303)


def _run_sync_check(conn, cur, user, b):
    """Recompute driver/guest location sync (VBA CheckLocationSync).

    Extracts coordinates from both saved links, computes the haversine
    distance, updates bookings.location_sync and queues a RED FLAG alert
     (Ops + Guest Admin) when the distance exceeds the 100 m threshold.
    Returns the gps_report dict.
    """
    driver_link = (b.get("driver_live_location") or "").strip()
    guest_link = (b.get("guest_live_location") or "").strip()
    report = gps_report(driver_link, guest_link, b.get("location_sync") or "")
    if report["distance_m"] is not None:
        cur.execute(
            "UPDATE bookings SET location_sync=:1 WHERE booking_id=:2",
            (report["status"], b.get("booking_id")),
        )
        if report["status"] == "RED FLAG":
            notify.notify_red_flag(
                conn, user,
                dict(b, driver_live_location=driver_link,
                     guest_live_location=guest_link), report)
    return report


@router.post("/{booking_id}/check-sync")
def check_sync(request: Request, booking_id: str):
    """On-demand location sync check (VBA CheckLocationSync button)."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_allocate(user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(booking_id)):
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    report = _run_sync_check(conn, cur, user, b)
    dist = report["distance_m"]
    audit(conn, user, "Location Sync Checked", booking_id,
          f"sync={report['status']}; dist={dist}")
    conn.commit()
    conn.close()
    if dist is None:
        msg = "sync-links-missing"
    elif report["status"] == "RED FLAG":
        msg = "sync-red-flag"
    else:
        msg = "sync-synced"
    return RedirectResponse(url=f"/bookings/{booking_id}?msg={msg}",
                            status_code=303)


@router.post("/{booking_id}/allocate/vendor")
def allocate_vendor(
    request: Request, booking_id: str,
    vendor_name: str = Form(""),
    vendor_contact: str = Form(""),
    vendor_email: str = Form(""),
    vendor_pkg_type: str = Form(""),
    confirm_sla: str = Form(""),
    confirm_lead: str = Form(""),
):
    """Step 2: allocate a vendor. Mirrors VBA SubmitBooking2.

    From 'Vehicle & Driver Allocation Pending' the vendor is recorded and the
    booking moves to 'Awaiting Driver & Vehicle Allocation' (stays 1-Pending).

    SLA RED FLAG (VBA): if the booking was created more than 30 minutes ago
    (step1_time) the submitter must explicitly confirm via the 'confirm_sla'
    checkbox, mirroring the VBA "Submit anyway?" prompt.

    Lead-time RED FLAG: booking->pickup must provide >= 10 hrs (same day) or
    >= 1 calendar day (different day); otherwise 'confirm_lead' is required.
    On success the vendor's vehicle/driver-details deadline is recorded:
      6 hrs before pickup (same day / pickup after noon) or
      11 PM the day prior to pickup (different day, pickup before noon).
    """
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_allocate(user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(booking_id)):
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    reason = (b.get("status_reason") or "").strip()
    ok_step = (
        (b.get("booking_status") or "").strip() == "1-Pending"
        and reason in ("Vehicle & Driver Allocation Pending",
                       "Awaiting Driver & Vehicle Allocation",
                       sla.REALLOC_REASON)
    )
    if not ok_step:
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-in-step2",
                                status_code=303)
    if not (vendor_name or "").strip():
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=missing-vendor",
                                status_code=303)
    # Auto-store new vendor in masters if not already present
    vname = vendor_name.strip()
    cur.execute(
        "SELECT vendor_name FROM vendors WHERE UPPER(TRIM(vendor_name))=UPPER(TRIM(:1))",
        (vname,),
    )
    if not cur.fetchone():
        vid = next_vendor_id(cur)
        cur.execute(
            "INSERT INTO vendors (vendor_id, tenant_id, vendor_name, status) VALUES (:1, :2, :3, 'Active')",
            (vid, user.get("tenant_id") or "TEN-RENTA-GO", vname),
        )
    elapsed = _sla_elapsed_minutes(cur, booking_id)
    if elapsed is not None and elapsed > 30 \
            and (confirm_sla or "").strip().lower() not in ("1", "true", "yes", "on"):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=sla-red-flag",
                                status_code=303)
    elig = _allocation_eligibility(cur, b)
    if not elig.get("eligible") \
            and (confirm_lead or "").strip().lower() not in ("1", "true", "yes", "on"):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=lead-red-flag",
                                status_code=303)
    deadline_text = ""
    if elig.get("vendor_deadline"):
        deadline_text = elig["vendor_deadline"].strftime("%d-%m-%Y %I:%M %p")
    override = "Y" if (confirm_lead or "").strip().lower() in ("1", "true", "yes", "on") else ""
    cur.execute(
        "UPDATE bookings SET vendor_name=:1, vendor_contact=:2, vendor_email=:3, "
        "vendor_pkg_type=:4, vendor_deadline=:5, alloc_lead_override=:6, "
        "step2_time=:7, "
        "booking_status='1-Pending', "
        "status_reason='Awaiting Driver & Vehicle Allocation', done_by_vendor=:8 "
        "WHERE booking_id=:9",
        (vendor_name.strip(), vendor_contact.strip(), vendor_email.strip(),
         vendor_pkg_type.strip(), deadline_text, override, datetime.now(),
         user["user_id"], booking_id),
    )
    audit(conn, user, "Vendor Allocated (Step 2)", booking_id,
          f"{vendor_name.strip()} | pkg {vendor_pkg_type.strip() or '-'}"
          + (" | LEAD OVERRIDE" if override else ""))
    complete_for_entity(conn, "BOOKING", booking_id, ("BOOKING_CREATED",), "Vendor allocated")
    emit_start(conn, "VENDOR_ALLOCATED", "BOOKING", booking_id,
               context={"booking_type": b.get("booking_type"), "corporate_id": b.get("company_id"),
                        "vendor_name": vendor_name.strip(), "policy_category": "Booking"})
    notify.notify_step2(conn, user, dict(b, vendor_name=vendor_name.strip(),
                                         vendor_contact=vendor_contact.strip(),
                                         vendor_email=vendor_email.strip(),
                                         vendor_pkg_type=vendor_pkg_type.strip()))
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=step2-done&notify=1", status_code=303)


@router.post("/{booking_id}/allocate/driver")
def allocate_driver(
    request: Request, booking_id: str,
    driver_name: str = Form(""),
    driver_contact: str = Form(""),
    vehicle_no: str = Form(""),
    driver_reporting_time: str = Form(""),
    driver_instructions: str = Form(""),
    special_instructions: str = Form(""),
    driver_photo: str = Form(""),
    vehicle_photo: str = Form(""),
    confirm_lead: str = Form(""),
):
    """Step 3: allocate driver & vehicle and confirm the booking.

    Mirrors VBA SubmitBooking3: requires driver name + vehicle no, sets the
    booking to '2-Confirmed / Booking Confirmed - Driver & Vehicle Allocated'
    and adds a trips row (AddToTrips) with the route map link and a computed
    driver reporting time (15 min before pickup).

    The lead-time eligibility gate (same rule as Step 2) applies unless the
    booking already carries a confirmed override (alloc_lead_override = 'Y').
    """
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_allocate(user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(booking_id)):
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    reason = (b.get("status_reason") or "").strip()
    if (b.get("booking_status") or "").strip() != "1-Pending" \
            or reason != "Awaiting Driver & Vehicle Allocation":
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-in-step2",
                                status_code=303)
    if not (driver_name or "").strip() or not (vehicle_no or "").strip():
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=missing-driver-vehicle",
                                status_code=303)
    elig = _allocation_eligibility(cur, b)
    overridden = (b.get("alloc_lead_override") or "").strip().upper() == "Y"
    if not elig.get("eligible") and not overridden \
            and (confirm_lead or "").strip().lower() not in ("1", "true", "yes", "on"):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=lead-red-flag",
                                status_code=303)
    # Auto-store new driver in masters if not already present
    dname = driver_name.strip()
    cur.execute(
        "SELECT driver_name FROM drivers WHERE UPPER(TRIM(driver_name))=UPPER(TRIM(:1))",
        (dname,),
    )
    if not cur.fetchone():
        did = next_driver_id(cur)
        cur.execute(
            "INSERT INTO drivers (driver_id, tenant_id, driver_name, status) VALUES (:1, :2, :3, 'Active')",
            (did, user.get("tenant_id") or "TEN-RENTA-GO", dname),
        )
    # Auto-store new vehicle reg number in masters if not already present
    vno = vehicle_no.strip()
    cur.execute(
        "SELECT reg_number FROM vehicles WHERE UPPER(TRIM(reg_number))=UPPER(TRIM(:1))",
        (vno,),
    )
    if not cur.fetchone():
        vid = next_vehicle_id(cur)
        cur.execute(
            "INSERT INTO vehicles (vehicle_id, tenant_id, reg_number, status) VALUES (:1, :2, :3, 'Active')",
            (vid, user.get("tenant_id") or "TEN-RENTA-GO", vno),
        )
    report_time = driver_reporting_time.strip() or _driver_reporting_time(b.get("pickup_time"))
    override = "Y" if (confirm_lead or "").strip().lower() in ("1", "true", "yes", "on") else ""
    cur.execute(
        "UPDATE bookings SET driver_name=:1, driver_contact=:2, vehicle_no=:3, "
        "driver_reporting_time=:4, alloc_lead_override=:5, "
        "driver_instructions=:6, special_instructions=:7, "
        "driver_photo=:8, vehicle_photo=:9, "
         "booking_status='2-Confirmed', "
         "status_reason='Booking Confirmed - Driver & Vehicle Allocated', step3_time=:10, done_by_driver=:11 "
          "WHERE booking_id=:12",
        (driver_name.strip(), driver_contact.strip(), vehicle_no.strip(),
         report_time, override,
         driver_instructions.strip() or None, special_instructions.strip() or None,
         driver_photo.strip() or None, vehicle_photo.strip() or None,
          datetime.now(), user["user_id"], booking_id),
    )
    _add_to_trips_for_booking(conn, b, driver_name.strip(), driver_contact.strip(),
                               vehicle_no.strip(), report_time)
    # tracking token for the one-tap GPS tracking links (driver T-2h window)
    import uuid as _uuid
    cur.execute(
        "UPDATE bookings SET track_token=:1 WHERE booking_id=:2 "
        "AND (track_token IS NULL OR track_token=' ')",
        (_uuid.uuid4().hex[:32], booking_id),
    )


@router.get("/{booking_id}/driver-profile")
def driver_profile(request: Request, booking_id: str):
    user = current_user(request)
    role = (user or {}).get("role", "").strip().lower()
    if not user or not (role == "guest" or _is_corporate(user) or _is_rentago_override(user)):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    booking = _get_booking(cur, booking_id)
    if not booking or not can_view(visible_booking_ids(user, cur), str(booking_id)):
        conn.close(); return RedirectResponse(url="/bookings", status_code=303)
    driver_name = (booking.get("driver_name") or "").strip()
    cur.execute(
        "SELECT driver_name,mobile,languages_known,passport_photo_path,license_expiry,police_verification,background_check,status,compliance_status "
        "FROM drivers WHERE UPPER(TRIM(driver_name))=UPPER(TRIM(:1)) FETCH FIRST 1 ROWS ONLY", (driver_name,))
    row = cur.fetchone()
    if not row:
        conn.close(); return RedirectResponse(url=f"/bookings/{booking_id}?msg=driver-profile-not-found", status_code=303)
    cur.execute("SELECT COUNT(1) FROM trips WHERE UPPER(TRIM(driver_name))=UPPER(TRIM(:1)) AND trip_status='Trip Completed'", (driver_name,))
    completed = int(cur.fetchone()[0] or 0)
    today = datetime.now().date()
    license_expiry = row[4].date() if hasattr(row[4], "date") else row[4]
    driver_compliance = bool((row[8] or "").strip().lower() == "yes" or ((not row[8] or row[8].strip().lower() == "pending") and (row[7] or "Active").strip().lower() == "active" and
                             (not license_expiry or license_expiry >= today) and
                             str(row[5] or "").lower() not in ("no", "failed", "expired") and
                             str(row[6] or "").lower() not in ("no", "failed", "expired")))
    cur.execute("SELECT insurance_exp,permit_exp,fitness_exp,puc_exp,status,compliance_status FROM vehicles WHERE UPPER(TRIM(reg_number))=UPPER(TRIM(:1)) FETCH FIRST 1 ROWS ONLY", (booking.get("vehicle_no") or ""))
    vehicle = cur.fetchone()
    vehicle_compliance = False
    if vehicle:
        expiries = [v.date() if hasattr(v, "date") else v for v in vehicle[:4] if v]
        vehicle_compliance = bool((vehicle[5] or "").strip().lower() == "yes" or ((not vehicle[5] or vehicle[5].strip().lower() == "pending") and (vehicle[4] or "Active").strip().lower() == "active" and all(v >= today for v in expiries)))
    conn.close()
    profile = {"name": row[0] or driver_name, "contact": row[1] or booking.get("driver_contact"),
               "languages": row[2] or "Not recorded", "photo": row[3] or booking.get("driver_photo"),
               "completed": completed, "driver_compliance": "Yes" if driver_compliance else "No",
               "vehicle_compliance": "Yes" if vehicle_compliance else "No", "vehicle_no": booking.get("vehicle_no")}
    return templates.TemplateResponse("bookings/driver_profile.html", {"request": request, "user": user, "booking": booking, "profile": profile, "from_mobile": request.query_params.get("from") == "mobile"})


@router.post("/{booking_id}/recalculate-planned-route")
def recalculate_planned_route(request: Request, booking_id: str):
    user = current_user(request)
    if not user or not _is_rentago_override(user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close(); return RedirectResponse(url="/bookings", status_code=303)
    stops = _planned_stops(
        b.get("pickup_address"), b.get("pickup_city"), b.get("pickup_state"), "India", b.get("pickup_gps"),
        [(b.get(f"pickup_{i}"), "") for i in range(1, 6)],
        b.get("drop_address"), b.get("drop_city"), b.get("drop_state"), "India", b.get("drop_gps"),
        [(b.get(f"drop_{i}"), "") for i in range(1, 6)])
    kms, hours, source, legs = route_estimate_multi(stops)
    payload = _planned_route_payload(stops, legs)
    cur.execute("UPDATE bookings SET planned_kms=:1, planned_hrs=:2, planned_route_source=:3, planned_route_json=:4 WHERE booking_id=:5",
                (kms, hours, source, payload, booking_id))
    audit(conn, user, "Planned Route Recalculated", booking_id, f"kms={kms}; legs={len(legs)}")
    conn.commit(); conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=route-recalculated", status_code=303)
    audit(conn, user, "Driver & Vehicle Allocated (Step 3)", booking_id,
          f"{driver_name.strip()} / {vehicle_no.strip()}"
          + (" | LEAD OVERRIDE" if override else ""))
    complete_for_entity(conn, "BOOKING", booking_id, ("VENDOR_ALLOCATED",), "Driver and vehicle allocated")
    emit_start(conn, "DRIVER_ALLOCATED", "BOOKING", booking_id,
               context={"booking_type": b.get("booking_type"), "corporate_id": b.get("company_id"),
                         "vehicle_type": b.get("vehicle_type"), "policy_category": "Booking"})
    emit_start(conn, "CUSTOMER_CONFIRMATION_REQUIRED", "BOOKING", booking_id,
               context={"booking_type": b.get("booking_type"), "corporate_id": b.get("company_id"),
                        "policy_category": "Booking"})
    notify.notify_step3(conn, user, dict(b, driver_name=driver_name.strip(),
                                         driver_contact=driver_contact.strip(),
                                         vehicle_no=vehicle_no.strip(),
                                         driver_reporting_time=report_time))
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/bookings/{booking_id}?msg=confirmed-allocated&notify=1",
                            status_code=303)


# ---------------------------------------------------------------------------
# Cancellation (SOP section 6)
# ---------------------------------------------------------------------------
def _detect_cancellation_code(b):
    """Auto-detect the cancellation reason code from booking state (VBA port).

    1: pending (no step 3)          2/3: confirmed, split at 6 hrs to pickup
    6: trip in progress / started   4/5 need human input (default 3/2 by time).
    """
    status = (b.get("booking_status") or "").strip()
    reason = (b.get("status_reason") or "").strip()
    if status == "1-Pending":
        return 1
    if reason in ("Guest Trip Started - Awaiting Driver Confirmation",
                  "Trip In Progress",
                  "Guest Trip Ended - Awaiting Driver Confirmation"):
        return 6
    if status == "2-Confirmed":
        pickup_dt = _pickup_datetime(b)
        if pickup_dt is not None:
            hours_left = (pickup_dt - datetime.now()).total_seconds() / 3600.0
            return 2 if hours_left >= 6 else 3
        return 2
    return 1


@router.post("/{booking_id}/cancel")
def cancel_booking(
    request: Request, booking_id: str,
    reason_code: str = Form(""),
    confirm: str = Form(""),
):
    """Cancel a booking (SOP section 6). Mirrors VBA CancelBooking.

    Auto-detects the policy code from the booking state unless an explicit
    reason_code (1-6) is supplied, applies the policy charge, generates the
    cancellation invoice, and marks the booking '3-Cancelled'.
    """
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if not _can_modify_booking(user):
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=not-allowed",
                                status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    b = _get_booking(cur, booking_id)
    if not b:
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(booking_id)):
        conn.close()
        return RedirectResponse(url="/bookings", status_code=303)
    status = (b.get("booking_status") or "").strip()
    if status.startswith("3-"):
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=already-cancelled",
                                status_code=303)
    if status == "2-Confirmed" and (b.get("status_reason") or "").strip() == "Trip Completed":
        conn.close()
        return RedirectResponse(url=f"/bookings/{booking_id}?msg=completed",
                                status_code=303)

    code = _detect_cancellation_code(b)
    if reason_code.strip().isdigit():
        try:
            supplied = int(reason_code.strip())
            if supplied in CANCELLATION_POLICY:
                code = supplied
        except Exception:
            pass
    desc, charges = CANCELLATION_POLICY[code]

    if (confirm or "").strip().lower() not in ("1", "true", "yes", "on"):
        conn.close()
        return RedirectResponse(
            url=f"/bookings/{booking_id}?msg=cancel-confirm&code={code}", status_code=303
        )

    now = datetime.now()
    rate = customer_rate(b.get("company_id"), b.get("vehicle_type"))
    refund = max(0.0, rate - charges) if rate else 0.0

    cur.execute(
        "UPDATE bookings SET booking_status='3-Cancelled', "
        "status_reason=:1, cancellation_reason=:2, cancellation_date=:3, "
        "done_by_booking=:4 WHERE booking_id=:5",
        (f"Booking Cancelled - Reason {code}: {desc}", desc, now,
         user["user_id"], booking_id),
    )
    cur.execute(
        "UPDATE trips SET trip_status='Cancelled', booking_status='Cancelled' "
        "WHERE booking_id=:1 AND trip_status NOT IN ('Trip Completed','Cancelled')",
        (booking_id,),
    )

    inv_id = _next_invoice_id(conn)
    cur.execute(
        """INSERT INTO invoices (
            invoice_id, booking_id, guest_name, company_name, pickup_address,
            drop_address, pickup_date, pickup_time, vehicle_type, package_type,
            cancellation_reason, cancellation_date, cancellation_policy,
            original_amount, cancellation_charges, refund_amount, invoice_status,
            payment_status, trip_end_date, vendor_expense_deadline,
            final_bill_deadline, toll, parking, extra_kms, extra_hours,
            other_expenses, total_vendor_expenses, final_amount
        ) VALUES (
            :1,:2,:3,:4,:5,:6,:7,:8,:9,:10,
            :11,:12,:13,
            :14,:15,:16,'Cancellation Invoice',:17,
            :18,:19,:20,
            0,0,0,0,0,0,:21
        )""",
        (
            inv_id, booking_id,
            (b.get("guest_name_1") or b.get("guest_name") or ""),
            (b.get("company_name") or ""),
            (b.get("pickup_address") or ""), (b.get("drop_address") or ""),
            b.get("pickup_date"), (b.get("pickup_time") or ""),
            (b.get("vehicle_type") or ""), (b.get("package_type") or
                                            b.get("vendor_pkg_type") or ""),
            desc, now, CANCELLATION_POLICY_TEXT,
            rate, charges, refund,
            "Cancellation Charges Due" if charges > 0 else "Closed - No Charges",
            now, now, now,
            charges,
        ),
    )
    audit(conn, user, "Booking Cancelled", booking_id,
          f"Reason {code}: {desc} | charges Rs.{charges:.0f} | invoice {inv_id}")
    complete_for_entity(conn, "BOOKING", booking_id, note="Booking cancelled; active SLA instances closed")
    emit_start(conn, "BOOKING_CANCELLED", "BOOKING", booking_id, department="Customer Service",
               context={"cancellation_code": code, "cancellation_charges": charges,
                        "refund_amount": refund, "policy_category": "Customer Service"})
    if refund > 0:
        emit_start(conn, "REFUND_REQUIRED", "INVOICE", inv_id, department="Finance",
                   context={"refund_amount": refund, "policy_category": "Finance"})
    notify.notify_cancellation(conn, user, b, code, desc, charges)
    conn.commit()
    conn.close()
    target = f"/bookings/{booking_id}?msg=cancelled&code={code}&inv={inv_id}"
    if charges:
        target += f"&chg={charges:.0f}"
    return RedirectResponse(url=target, status_code=303)


def _driver_reporting_time(pickup_time):
    """Compute driver reporting time = pickup time - 15 minutes (VBA AddToTrips)."""
    if not pickup_time:
        return ""
    t = str(pickup_time).strip()
    tm = None
    for fmt in ("%I:%M %p", "%I:%M%p", "%H:%M", "%H:%M:%S"):
        try:
            tm = datetime.strptime(t, fmt)
            break
        except Exception:
            continue
    if tm is None:
        return ""
    return (tm - timedelta(minutes=15)).strftime("%I:%M %p")


def _sla_elapsed_minutes(cur, booking_id):
    """Whole minutes elapsed between step1_time and now (None when unreadable).

    step1_time is Oracle DATE/TIMESTAMP; the raw subtraction can surface as an
    interval via the sqlplus wrapper, so fetch a formatted string instead and
    compute the elapsed time in Python.
    """
    try:
        cur.execute(
            "SELECT TO_CHAR(step1_time, 'YYYY-MM-DD HH24:MI:SS') FROM bookings "
            "WHERE booking_id=:1",
            (booking_id,),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        ref = datetime.strptime(str(row[0]).strip(), "%Y-%m-%d %H:%M:%S")
        return max(0, int((datetime.now() - ref).total_seconds() // 60))
    except Exception:
        return None


def _allocation_eligibility(cur, b, entry_s=None):
    """Evaluate the vehicle & driver allocation lead-time rules.

    Mirrors the product rules evaluated at booking-entry time:

      Same calendar day (booking date == pickup date):
        - eligible when booking->pickup is >= 10 hours
        - vendor must provide vehicle & driver details 6 hours before pickup

      Different calendar day (pickup date >= 1 day after booking date):
        - eligible given pickup is at least 1 calendar day later
        - pickup BEFORE noon (12:00 PM afternoon): vendor deadline is
          11 PM on the day prior to pickup
        - pickup AFTER noon: vendor deadline is 6 hours before pickup

    `entry_s` optionally supplies the pre-fetched step1_time string
    ('YYYY-MM-DD HH24:MI:SS'); when None it is queried here.

    Returns a dict with 'eligible', 'vendor_deadline' (datetime or None),
    'lead_kind' ('same-day' | 'next-day' | 'unknown'), and a readable 'detail'.
    """
    bid = b.get("booking_id")
    if entry_s is None:
        try:
            cur.execute(
                "SELECT TO_CHAR(step1_time, 'YYYY-MM-DD HH24:MI:SS') FROM bookings "
                "WHERE booking_id=:1",
                (bid,),
            )
            row = cur.fetchone()
            entry_s = str(row[0]).strip() if (row and row[0]) else ""
        except Exception:
            entry_s = ""
    booking_dt = None
    if entry_s:
        try:
            booking_dt = datetime.strptime(entry_s, "%Y-%m-%d %H:%M:%S")
        except Exception:
            booking_dt = None
    pickup_dt = _pickup_datetime(b)
    if booking_dt is None or pickup_dt is None:
        return {"eligible": True, "unknown": True, "lead_kind": "unknown",
                "vendor_deadline": None, "detail": "Lead time could not be evaluated."}

    if pickup_dt.date() == booking_dt.date():
        hours = (pickup_dt - booking_dt).total_seconds() / 3600.0
        detail = ("Booking {:%d-%m-%Y %H:%M} to pickup {:%d-%m-%Y %H:%M} "
                  "= {:.1f} hrs (need >= 10)").format(booking_dt, pickup_dt, hours)
        return {
            "eligible": hours >= 10, "lead_kind": "same-day", "hours": hours,
            "booking_dt": booking_dt, "pickup_dt": pickup_dt,
            "vendor_deadline": pickup_dt - timedelta(hours=6), "detail": detail,
        }

    day_diff = (pickup_dt.date() - booking_dt.date()).days
    before_noon = pickup_dt.hour < 12
    if before_noon:
        deadline = datetime.combine(pickup_dt.date() - timedelta(days=1), time(23, 0))
        rule = "pickup before noon -> deadline 11 PM day prior"
    else:
        deadline = pickup_dt - timedelta(hours=6)
        rule = "pickup after noon -> deadline 6 hrs before pickup"
    detail = ("Booking date {:%d-%m-%Y}, pickup date {:%d-%m-%Y} ({:d} day(s)), "
              "{}. ").format(booking_dt, pickup_dt, day_diff, rule)
    return {
        "eligible": day_diff >= 1, "lead_kind": "next-day",
        "day_diff": day_diff, "pickup_before_noon": before_noon,
        "booking_dt": booking_dt, "pickup_dt": pickup_dt,
        "vendor_deadline": deadline, "detail": detail,
    }


def _sync_trip_booking_details(conn, b):
    """Refresh editable booking details on an existing Trip without resetting status."""
    cur = conn.cursor()
    cur.execute("SELECT trip_id FROM trips WHERE booking_id=:1", (b.get("booking_id"),))
    if not cur.fetchone():
        return
    gmaps = "https://www.google.com/maps/dir/{}/{}".format(
        quote((b.get("pickup_address") or "").strip()), quote((b.get("drop_address") or "").strip()))
    cur.execute(
        "UPDATE trips SET guest_name=:1,pickup_date=:2,pickup_address=:3,drop_address=:4, "
        "google_maps_link=:5,planned_route_json=:6 WHERE booking_id=:7",
        (b.get("guest_name_1") or b.get("guest_name") or "", b.get("pickup_date"),
         b.get("pickup_address"), b.get("drop_address"), gmaps, b.get("planned_route_json"), b.get("booking_id")),
    )


def _ensure_vendor_invoice(conn, booking, now):
    """Create one draft vendor bill when a vendor trip is completed."""
    vendor_name = (booking.get("vendor_name") or "").strip()
    if not vendor_name:
        return None
    cur = conn.cursor()
    cur.execute("SELECT vendor_id FROM vendors WHERE UPPER(TRIM(vendor_name))=UPPER(TRIM(:1)) FETCH FIRST 1 ROWS ONLY", (vendor_name,))
    vendor = cur.fetchone()
    if not vendor:
        return None
    vendor_id = vendor[0]; tenant_id = booking.get("tenant_id") or "TEN-RENTA-GO"
    cur.execute("SELECT vendor_invoice_id FROM vendor_invoices WHERE vendor_id=:1 AND tenant_id=:2 AND booking_id=:3", (vendor_id, tenant_id, booking.get("booking_id")))
    existing = cur.fetchone()
    if existing:
        return existing[0]
    invoice_id = "VIN-" + uuid.uuid4().hex[:20]
    cur.execute(
        "INSERT INTO vendor_invoices (vendor_invoice_id,tenant_id,vendor_id,booking_id,invoice_number,invoice_date,status,created_by) "
        "VALUES (:1,:2,:3,:4,:5,:6,'Draft','SLA-ENGINE')",
        (invoice_id, tenant_id, vendor_id, booking.get("booking_id"), f"VI-{now:%Y%m%d%H%M%S}", now),
    )
    return invoice_id


def _add_to_trips_for_booking(conn, b, driver_name, driver_contact, vehicle_no, report_time):
    """Port of VBA AddToTrips: create/refresh the trips row for a confirmed booking."""
    cur = conn.cursor()
    gmaps = "https://www.google.com/maps/dir/{}/{}".format(
        quote((b.get("pickup_address") or "").strip()),
        quote((b.get("drop_address") or "").strip()),
    )
    cur.execute("SELECT trip_id FROM trips WHERE booking_id=:1", (b.get("booking_id"),))
    existing = cur.fetchone()
    if existing:
        cur.execute(
            "UPDATE trips SET guest_name=:1, pickup_date=:2, pickup_address=:3, "
            "drop_address=:4, driver_name=:5, vehicle_no=:6, booking_status=:7, "
            "trip_status=:8, driver_mobile=:9, driver_reporting_time=:10, "
            "google_maps_link=:11,planned_route_json=:12 WHERE booking_id=:13",
            (b.get("guest_name_1") or b.get("guest_name") or "", b.get("pickup_date"),
             b.get("pickup_address"), b.get("drop_address"), driver_name, vehicle_no,
             "2-Confirmed", "Confirmed", driver_contact, report_time, gmaps,
             b.get("planned_route_json"), b.get("booking_id")),
        )
        return
    trip_id = _next_trip_id(conn)
    cur.execute(
        """INSERT INTO trips (
            trip_id, tenant_id, booking_id, guest_name, pickup_date, pickup_address,
            drop_address, driver_name, vehicle_no, booking_status, trip_status,
            driver_mobile, driver_reporting_time, google_maps_link, planned_route_json
        ) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,:12,:13,:14,:15)""",
         (trip_id, b.get("tenant_id") or "TEN-RENTA-GO", b.get("booking_id"), b.get("guest_name_1") or b.get("guest_name") or "",
         b.get("pickup_date"), b.get("pickup_address"), b.get("drop_address"),
         driver_name, vehicle_no, "2-Confirmed", "Confirmed", driver_contact,
         report_time, gmaps, b.get("planned_route_json")),
    )


def _get_booking(cur, booking_id):
    cur.execute("SELECT * FROM bookings WHERE booking_id=:1", (booking_id,))
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0].lower() for d in cur.description]
    return dict(zip(cols, row))


def _find_trip_row(cur, booking_id):
    """Return the trips dict for a booking (if a trip row exists)."""
    cur.execute("SELECT * FROM trips WHERE booking_id=:1", (booking_id,))
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0].lower() for d in cur.description]
    return dict(zip(cols, row))


def _save_trip_actuals(conn, b, trip, now):
    """Mirrors VBA SaveTripActuals: compute and persist actual kms/hours on the
    trips row, and mark the booking's live-location map as inactive.

    actualKms  = round(drop_end_km - pickup_start_km, 1), min 0
    actualHours = round((now - pickupDate+pickupTime) in hours, 2), min 0
    """
    start_km = _as_float(trip.get("pickup_start_km"))
    end_km = _as_float(trip.get("drop_end_km"))
    actual_km = max(0.0, round(end_km - start_km, 1))

    pickup_dt = _pickup_datetime(b)
    actual_hrs = 0.0
    if pickup_dt is not None:
        mins = (now - pickup_dt).total_seconds() / 60.0
        actual_hrs = max(0.0, round(mins / 60.0, 2))

    cur = conn.cursor()
    cur.execute(
        "UPDATE trips SET actual_kms=:1, actual_hrs=:2, actual_end_dt=:3, "
        "driver_live_location=:4, guest_live_location=:5, location_sync=:6 "
        "WHERE trip_id=:7",
        (actual_km, actual_hrs, now,
         b.get("driver_live_location") or "", b.get("guest_live_location") or "",
         (b.get("location_sync") or "") or "Trips Live Location",
          trip.get("trip_id")),
    )
    cur.execute(
        "UPDATE bookings SET driver_live_location='', guest_live_location='', "
        "location_sync='Maps Inactive - Trip Completed' WHERE booking_id=:1",
        (b.get("booking_id"),),
    )


def _tracking_window_open(b, who):
    """Is live-tracking active for `who` at this moment relative to pickup?

    driver: open from pickup - 2 hours onward; guest: open from pickup - 15 min
    onward. After pickup the window stays open until the trip ends (the end-trip
    flow clears the live fields, so this only gates pre-start / ongoing saves).
    A missing/unknowable pickup time opens the window immediately.
    """
    pickup_dt = _pickup_datetime(b)
    if pickup_dt is None:
        return True
    lead = timedelta(hours=2) if who == "driver" else timedelta(minutes=15)
    return datetime.now() >= pickup_dt - lead


def _pickup_datetime(b):
    """Build a datetime from booking pickup_date (date or str) + pickup_time (str)."""
    try:
        d = b.get("pickup_date")
        t = str(b.get("pickup_time") or "").strip()
        if d is None or str(d).strip() == "":
            return None
        from datetime import datetime as _dt

        ddate = None
        if isinstance(d, str):
            ds = d.strip()
            if not ds:
                return None
            for dfmt in ("%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
                try:
                    ddate = _dt.strptime(ds, dfmt).date()
                    break
                except Exception:
                    continue
            if ddate is None:
                return None
        else:
            ddate = d.date() if hasattr(d, "date") else d

        if t:
            dt = _dt.combine(ddate, _dt.min.time())
            for fmt in ("%I:%M %p", "%H:%M", "%I:%M%p", "%H:%M:%S"):
                try:
                    tm = _dt.strptime(t, fmt).time()
                    dt = _dt.combine(dt.date(), tm)
                    return dt
                except Exception:
                    continue
            return dt
        return _dt.combine(ddate, _dt.min.time())
    except Exception:
        return None


def _as_float(v):
    try:
        return float(v) if v is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _next_invoice_id(conn):
    """Generate next invoice id (INV-xxxxxx) mirroring the VBA sequence."""
    cur = conn.cursor()
    cur.execute("SELECT invoice_id FROM invoices")
    max_num = 0
    for (iid,) in cur.fetchall():
        s = str(iid or "").strip()
        if s.startswith("INV-"):
            try:
                n = int(s[4:])
                if n > max_num:
                    max_num = n
            except Exception:
                pass
    return "INV-%06d" % (max_num + 1)


def _generate_provisional_invoice(conn, b, now):
    """Mirrors VBA GenerateProvisionalInvoice.

    Creates a 30-column invoice row with reference fields, the ratecard-based
    original amount, and the 48h/72h vendor/final deadlines. Returns the new
    invoice id (or None if the booking lacks required fields).
    """
    if not b or not b.get("booking_id"):
        return None
    inv_id = _next_invoice_id(conn)
    from datetime import timedelta

    vendor_deadline = now + timedelta(hours=48)
    final_deadline = now + timedelta(hours=72)
    rate = customer_rate(b.get("company_id"), b.get("vehicle_type"))
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO invoices (
            invoice_id, booking_id, guest_name, company_name, pickup_address,
            drop_address, pickup_date, pickup_time, vehicle_type, package_type,
            cancellation_reason, cancellation_date, cancellation_policy,
            original_amount, cancellation_charges, refund_amount, invoice_status,
            payment_status, trip_end_date, vendor_expense_deadline,
            final_bill_deadline, toll, parking, extra_kms, extra_hours,
            other_expenses, total_vendor_expenses, final_amount
        ) VALUES (
            :1,:2,:3,:4,:5,:6,:7,:8,:9,:10,
            '','','',
            :11,0,0,'Provisional Invoice','Pending Trip Expenses',
            :12,:13,:14,
            0,0,0,0,0,0,0
        )""",
        (
            inv_id,
            b.get("booking_id"),
            (b.get("guest_name_1") or b.get("guest_name") or ""),
            (b.get("company_name") or ""),
            (b.get("pickup_address") or ""),
            (b.get("drop_address") or ""),
            b.get("pickup_date"),
            (b.get("pickup_time") or ""),
            (b.get("vehicle_type") or ""),
            (b.get("package_type") or b.get("vendor_pkg_type") or ""),
            rate,
            now,
            vendor_deadline,
            final_deadline,
        ),
    )
    return inv_id
