"""Notifications outbox routes: list, mark-as-sent (SOP section 13).

Email/WhatsApp payloads are queued with ready mailto:/wa.me links; operations
click through to send manually until SMTP AUTH is enabled at the tenant level.
"""

from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth import current_user
from ..templating import templates
from ..db import get_connection
from ..scope import visible_booking_ids, can_view, OPERATOR_ROLES
from ..audit import audit
from ..notification_scope import can_see_notification

router = APIRouter(prefix="/notifications")

# Roles that see the full outbox; others only see rows for bookings they can view.
OUTBOX_ROLES = set(OPERATOR_ROLES) | {"vendor manager", "finance", "compliance"}


@router.get("")
def list_notifications(request: Request, event: str = "", status: str = ""):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    sql = (
        "SELECT notification_id, event, channel, booking_id, recipient_name, "
        "recipient_email, recipient_phone, subject, link, status, created_dt, created_by "
        "FROM notifications n"
    )
    params, conds = [], []
    role = (user.get("role") or "").strip().lower()
    if role in {"corporate admin", "corporate booking user", "corporate manager", "corporate viewer"}:
        tenant_id = str(user.get("tenant_id") or "").strip()
        user_id = str(user.get("user_id") or "").strip()
        email = str(user.get("email") or "").strip().lower()
        # Fail closed when the authenticated session has no unambiguous tenant.
        if not tenant_id or not user_id:
            conn.close()
            return templates.TemplateResponse(
                "notifications/list.html",
                {"request": request, "user": user, "notifications": [],
                 "event_filter": event, "status_filter": status},
            )
        params.extend([tenant_id, user_id, email])
        conds.append("n.tenant_id = :1")
        conds.append("(UPPER(n.created_by) = UPPER(:2) OR UPPER(n.recipient_email) = UPPER(:3))")
    if event:
        params.append("%" + event + "%")
        conds.append("LOWER(n.event) LIKE LOWER(:" + str(len(params)) + ")")
    if status:
        params.append("%" + status + "%")
        conds.append("LOWER(n.status) LIKE LOWER(:" + str(len(params)) + ")")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY n.notification_id DESC FETCH FIRST 300 ROWS ONLY"
    cur.execute(sql, params)
    rows = cur.fetchall()

    scoped = (user.get("role") or "").strip().lower() not in OUTBOX_ROLES
    if scoped:
        visible = visible_booking_ids(user, cur)
        rows = [r for r in rows if can_view(visible, str(r[3] or ""))]
    rows = [r for r in rows if can_see_notification(user, r[1])]
    conn.close()

    notifications = [{
        "notification_id": r[0], "event": r[1], "channel": r[2],
        "booking_id": r[3], "recipient_name": r[4], "recipient_email": r[5],
        "recipient_phone": r[6], "subject": r[7], "link": r[8],
        "status": r[9], "created_dt": r[10], "created_by": r[11],
    } for r in rows]
    return templates.TemplateResponse(
        "notifications/list.html",
        {"request": request, "user": user, "notifications": notifications,
         "event_filter": event, "status_filter": status},
    )


@router.post("/{notification_id}/sent")
def mark_sent(request: Request, notification_id: str):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if (user.get("role") or "").strip().lower() not in OUTBOX_ROLES:
        return RedirectResponse(url="/notifications", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE notifications SET status='Sent Manually' WHERE notification_id=:1",
        (notification_id,),
    )
    # Auto-stamp ack_sent_time on the booking if this is a step1 notification
    # (event now carries the recipient: step1-Guest / step1-Admin)
    cur.execute(
        "SELECT event, booking_id FROM notifications WHERE notification_id=:1",
        (notification_id,),
    )
    row = cur.fetchone()
    if row and str(row[0]).strip().lower().startswith("step1") and row[1]:
        cur.execute(
            "UPDATE bookings SET ack_sent_time=SYSDATE WHERE booking_id=:1 AND ack_sent_time IS NULL",
            (row[1],),
        )
    audit(conn, user, "Notification Sent", notification_id, "")
    conn.commit()
    conn.close()
    return RedirectResponse(url="/notifications", status_code=303)
