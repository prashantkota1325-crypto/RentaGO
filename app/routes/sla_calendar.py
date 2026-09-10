"""SLA working-hours and holiday calendar administration."""

from datetime import datetime

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates
from ..audit import audit

router = APIRouter(prefix="/sla/calendars")


def allowed(user):
    return bool(user) and module_level(user, "SLA Dashboard") == "F"


@router.get("")
def calendar_page(request: Request):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT department, day_of_week, start_minute, end_minute, timezone FROM sla_working_hours ORDER BY department, day_of_week")
    hours = [dict(zip(("department", "day", "start", "end", "timezone"), r)) for r in cur.fetchall()]
    cur.execute("SELECT holiday_date, holiday_name, department, is_working_day FROM sla_holidays ORDER BY holiday_date")
    holidays = [dict(zip(("date", "name", "department", "working"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("sla/calendars.html", {"request": request, "user": user, "hours": hours, "holidays": holidays})


@router.post("/hours")
def save_hours(request: Request, department: str = Form(...), day: int = Form(...),
               start_minute: int = Form(...), end_minute: int = Form(...),
               timezone: str = Form("Asia/Kolkata")):
    user = current_user(request)
    if not allowed(user) or not 0 <= day <= 6 or not 0 <= start_minute <= 1440 or not 0 <= end_minute <= 1440 or end_minute <= start_minute:
        return RedirectResponse("/sla/calendars?msg=invalid", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "MERGE INTO sla_working_hours h USING (SELECT :1 department,:2 day_of_week FROM dual) x "
        "ON (h.department=x.department AND h.day_of_week=x.day_of_week) "
        "WHEN MATCHED THEN UPDATE SET start_minute=:3,end_minute=:4,timezone=:5 "
        "WHEN NOT MATCHED THEN INSERT (department,day_of_week,start_minute,end_minute,timezone) VALUES (:6,:7,:8,:9,:10)",
        (department, day, start_minute, end_minute, timezone, department, day, start_minute, end_minute, timezone),
    )
    audit(conn, user, "SLA Working Hours Updated", department, f"day={day}; {start_minute}-{end_minute}")
    conn.commit(); conn.close()
    return RedirectResponse("/sla/calendars?msg=saved", status_code=303)


@router.post("/holidays")
def add_holiday(request: Request, holiday_date: str = Form(...), holiday_name: str = Form(...),
                department: str = Form(""), is_working_day: str = Form("N")):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    try:
        day = datetime.strptime(holiday_date, "%Y-%m-%d").date()
    except ValueError:
        return RedirectResponse("/sla/calendars?msg=invalid", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "MERGE INTO sla_holidays h USING (SELECT :1 holiday_date FROM dual) x "
        "ON (h.holiday_date=x.holiday_date) WHEN MATCHED THEN UPDATE SET holiday_name=:2,department=:3,is_working_day=:4 "
        "WHEN NOT MATCHED THEN INSERT (holiday_date,holiday_name,department,is_working_day) VALUES (:5,:6,:7,:8)",
        (day, holiday_name.strip(), department.strip() or None, is_working_day[:1].upper(),
         day, holiday_name.strip(), department.strip() or None, is_working_day[:1].upper()),
    )
    audit(conn, user, "SLA Holiday Updated", holiday_date, holiday_name[:500])
    conn.commit(); conn.close()
    return RedirectResponse("/sla/calendars?msg=saved", status_code=303)
