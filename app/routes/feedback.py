"""RentaGO internal feedback review, follow-up, and rectification tool."""

from datetime import datetime

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates
from ..audit import audit
from ..sla_engine import complete_for_entity

router = APIRouter(prefix="/feedback")
FEEDBACK_STATUSES = ("Open", "Under Review", "Action Required", "Rectified", "Closed")


def _allowed(user):
    return bool(user) and module_level(user, "Feedback") is not None


@router.get("")
def feedback_list(request: Request, status: str = "", q: str = "",
                  owner_group: str = "", safety: str = ""):
    user = current_user(request)
    if not _allowed(user):
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    sql = (
        "SELECT t.trip_id, t.booking_id, b.guest_name_1, b.company_name, "
        "b.vendor_name, b.driver_name, t.guest_rating, t.guest_feedback, "
        "t.feedback_went_well, t.feedback_improvements, t.safety_status, "
        "t.safety_issues, t.incident_priority, t.incident_status, "
        "t.feedback_owner_group, "
        "NVL(t.feedback_status,'Open'), t.feedback_owner, t.feedback_action, "
        "t.feedback_followup_date, t.feedback_closed_on "
        "FROM trips t JOIN bookings b ON b.booking_id=t.booking_id "
        "WHERE t.guest_rating IS NOT NULL"
    )
    params = []
    if status:
        params.append(status)
        sql += " AND NVL(t.feedback_status,'Open')=:{0}".format(len(params))
    if owner_group in ("RentaGO Team", "Vendor", "Driver"):
        params.append(owner_group)
        sql += " AND NVL(t.feedback_owner_group,'RentaGO Team')=:{0}".format(len(params))
    if safety in ("Yes", "Some concern", "Safety issue"):
        params.append(safety)
        sql += " AND t.safety_status=:{0}".format(len(params))
    if q:
        params.append("%" + q.strip() + "%")
        n = len(params)
        sql += f" AND (LOWER(b.guest_name_1) LIKE LOWER(:{n}) OR LOWER(b.company_name) LIKE LOWER(:{n}) OR LOWER(t.booking_id) LIKE LOWER(:{n}))"
    sql += " ORDER BY t.trip_id DESC FETCH FIRST 500 ROWS ONLY"
    cur.execute(sql, params or None)
    rows = cur.fetchall()
    conn.close()
    feedback = [dict(zip(("trip_id", "booking_id", "guest", "company", "vendor",
                          "driver", "rating", "comments", "went_well", "improvements",
                          "safety_status", "safety_issues", "priority", "incident_status", "owner_group",
                          "status", "owner", "action", "followup", "closed"), r)) for r in rows]
    return templates.TemplateResponse(
        "feedback/list.html", {"request": request, "user": user,
        "feedback": feedback, "statuses": FEEDBACK_STATUSES,
         "status_filter": status, "query": q, "owner_group_filter": owner_group,
         "safety_filter": safety},
    )


@router.post("/{trip_id}/update")
def update_feedback(request: Request, trip_id: str, status: str = Form("Open"),
                    owner: str = Form(""), action: str = Form(""),
                    followup_date: str = Form(""), owner_group: str = Form("RentaGO Team")):
    user = current_user(request)
    if not _allowed(user) or status not in FEEDBACK_STATUSES:
        return RedirectResponse(url="/feedback?msg=not-allowed", status_code=303)
    followup = None
    if followup_date.strip():
        try:
            followup = datetime.strptime(followup_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            return RedirectResponse(url="/feedback?msg=invalid-date", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT booking_id FROM trips WHERE trip_id=:1", (trip_id,))
    booking_row = cur.fetchone()
    cur.execute(
        "UPDATE trips SET feedback_status=:1, feedback_owner=:2, feedback_action=:3, "
        "feedback_followup_date=:4, feedback_closed_on=:5, feedback_owner_group=:6 "
        "WHERE trip_id=:7 AND guest_rating IS NOT NULL",
        (status, owner.strip() or None, action.strip()[:2000] or None, followup,
         datetime.now().date() if status == "Closed" else None, owner_group, trip_id),
    )
    audit(conn, user, "Feedback Follow-up Updated", trip_id,
          f"status={status}; owner={owner.strip() or '-'}")
    if status == "Closed" and booking_row and booking_row[0]:
        complete_for_entity(conn, "BOOKING", booking_row[0], ("FEEDBACK_SUBMITTED",), "Feedback follow-up closed")
    conn.commit()
    conn.close()
    return RedirectResponse(url="/feedback?msg=updated", status_code=303)
