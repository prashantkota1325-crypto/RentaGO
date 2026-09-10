"""SLA notification outbox monitoring."""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates
from ..audit import audit

router = APIRouter(prefix="/sla/notification-queue")


@router.get("")
def queue(request: Request, status: str = ""):
    user = current_user(request)
    if not user or module_level(user, "SLA Dashboard") != "F":
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT status, COUNT(1) FROM notifications GROUP BY status ORDER BY status")
    counts = {str(r[0]): int(r[1]) for r in cur.fetchall()}
    sql = "SELECT notification_id,event,channel,recipient_name,recipient_email,status,attempts,last_attempt,error_message,created_dt FROM notifications"
    params = []
    if status:
        sql += " WHERE status=:1"; params.append(status)
    sql += " ORDER BY created_dt DESC FETCH FIRST 500 ROWS ONLY"
    cur.execute(sql, params or None)
    rows = [dict(zip(("notification_id", "event", "channel", "recipient", "email", "status", "attempts", "last_attempt", "error", "created_dt"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("sla/notification_queue.html", {"request": request, "user": user, "counts": counts, "rows": rows, "status_filter": status})


@router.post("/{notification_id}/retry")
def retry(request: Request, notification_id: str):
    user = current_user(request)
    if not user or module_level(user, "SLA Dashboard") != "F":
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "UPDATE notifications SET status='Queued', attempts=0, last_attempt=NULL, error_message=NULL "
        "WHERE notification_id=:1 AND status IN ('Failed','Manual')", (notification_id,))
    if cur.rowcount:
        audit(conn, user, "SLA Notification Manually Retried", notification_id, "")
    conn.commit(); conn.close()
    return RedirectResponse("/sla/notification-queue", status_code=303)
