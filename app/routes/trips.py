"""Trip routes: list and trip detail views."""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth import current_user, module_level
from ..templating import templates
from ..db import get_connection
from ..scope import visible_booking_ids, can_view, is_internal_user
from ..dashboard_metrics import booking_trip_kpis, can_view_booking_kpis

router = APIRouter(prefix="/trips")


@router.get("")
def list_trips(request: Request, status: str = "", q: str = "", kpi: str = ""):
    """List trips, optionally filtered by status and/or guest/booking text."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if (user.get("role") or "").strip().lower() in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}:
        return RedirectResponse(url="/dashboards/vendor", status_code=303)
    if module_level(user, "Trips") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    sql = (
        "SELECT trip_id, booking_id, guest_name, pickup_date, pickup_address, "
         "drop_address, driver_name, vehicle_no, trip_status, booking_status, trip_remarks "
        "FROM trips"
    )
    params = []
    conds = []
    if user.get("tenant_id") and (user.get("role") or "").strip().lower() != "super admin":
        params.append(user["tenant_id"]); conds.append(f"tenant_id=:{len(params)}")
    if status:
        params.append("%" + status + "%")
        conds.append("UPPER(trip_status) LIKE UPPER(:" + str(len(params)) + ")")
    if q:
        params.append("%" + q + "%"); first = len(params)
        params.append("%" + q + "%"); second = len(params)
        conds.append(f"(LOWER(guest_name) LIKE LOWER(:{first}) OR LOWER(booking_id) LIKE LOWER(:{second}))")
    kpi_conditions = {
        "completed": "trip_status='Trip Completed'",
        "cancelled": "trip_status='Cancelled'",
        "pending": "(trip_status LIKE '%Pending%' OR booking_status LIKE '%Pending%')",
        "current": "trip_status NOT IN ('Trip Completed','Cancelled') AND TRUNC(pickup_date)=TRUNC(SYSDATE)",
        "current_pending": "(trip_status LIKE '%Pending%' OR booking_status LIKE '%Pending%') AND TRUNC(pickup_date)=TRUNC(SYSDATE)",
        "in_progress": "trip_status='In Progress'",
        "pickup_passed": "trip_status NOT IN ('Trip In Progress','Trip Completed','Cancelled') AND TRUNC(pickup_date)=TRUNC(SYSDATE) AND REGEXP_LIKE(TRIM(pickup_start_time),'^[0-9]{1,2}:[0-9]{2}$') AND TO_DATE(TO_CHAR(pickup_date,'YYYY-MM-DD')||' '||TRIM(pickup_start_time),'YYYY-MM-DD HH24:MI') < SYSDATE",
    }
    if kpi in kpi_conditions:
        conds.append(kpi_conditions[kpi])
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY trip_id DESC FETCH FIRST 500 ROWS ONLY"
    cur.execute(sql, params)
    rows = cur.fetchall()

    visible = visible_booking_ids(user, cur)
    kpis = booking_trip_kpis(cur, user) if can_view_booking_kpis(user) else None
    conn.close()

    trips = []
    for r in rows:
        if not can_view(visible, str(r[1])):
            continue
        trips.append({
            "trip_id": r[0], "booking_id": r[1], "guest_name": r[2],
            "pickup_date": r[3], "pickup_address": r[4], "drop_address": r[5],
            "driver_name": r[6], "vehicle_no": r[7], "trip_status": r[8],
            "booking_status": r[9], "trip_remarks": r[10],
        })
    return templates.TemplateResponse(
        "trips/list.html",
         {"request": request, "user": user, "trips": trips, "status_filter": status, "query": q, "kpi": kpi, "kpis": kpis,
         "show_kpis": can_view_booking_kpis(user)},
    )


@router.get("/{trip_id}")
def trip_detail(request: Request, trip_id: str):
    """Show full details of a single trip."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if (user.get("role") or "").strip().lower() in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}:
        return RedirectResponse(url="/dashboards/vendor", status_code=303)
    if module_level(user, "Trips") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trips WHERE trip_id=:1", (trip_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return templates.TemplateResponse(
            "trips/not_found.html", {"request": request, "user": user}
        )
    cols = [d[0].lower() for d in cur.description]
    data = dict(zip(cols, row))
    if (user.get("tenant_id") and (user.get("role") or "").strip().lower() != "super admin"
            and str(data.get("tenant_id") or "") != str(user["tenant_id"])):
        conn.close()
        return templates.TemplateResponse("trips/not_found.html", {"request": request, "user": user})
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(data.get("booking_id") or "")):
        conn.close()
        return templates.TemplateResponse(
            "trips/not_found.html", {"request": request, "user": user}
        )
    conn.close()
    return templates.TemplateResponse(
        "trips/detail.html", {"request": request, "user": user, "t": data}
    )
