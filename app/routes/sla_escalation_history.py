"""Operational SLA escalation acknowledgment and closure."""

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.responses import Response
import csv
import io

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates
from ..audit import audit

router = APIRouter(prefix="/sla/escalation-history")


def allowed(user):
    return bool(user) and module_level(user, "SLA Dashboard") == "F"


@router.get("")
def history(request: Request, status: str = "", export: str = ""):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    sql = (
        "SELECT e.escalation_id,e.instance_id,e.escalation_level,e.status,e.triggered_at,e.message, "
        "i.entity_type,i.entity_id,i.priority FROM sla_escalations e "
        "JOIN sla_instances i ON i.instance_id=e.instance_id")
    params = []
    if status:
        sql += " WHERE e.status=:1"; params.append(status)
    sql += " ORDER BY e.triggered_at DESC FETCH FIRST 500 ROWS ONLY"
    cur.execute(sql, params or None)
    rows = [dict(zip(("escalation_id", "instance_id", "level", "status", "triggered_at", "message", "entity_type", "entity_id", "priority"), r)) for r in cur.fetchall()]
    if export:
        buf = io.StringIO(); writer = csv.DictWriter(buf, fieldnames=tuple(rows[0].keys()) if rows else ("escalation_id", "instance_id", "level", "status", "triggered_at", "message", "entity_type", "entity_id", "priority")); writer.writeheader(); writer.writerows(rows)
        conn.close()
        return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="rentago-sla-escalations.csv"'})
    conn.close()
    return templates.TemplateResponse("sla/escalation_history.html", {"request": request, "user": user, "rows": rows, "status_filter": status})


@router.post("/{escalation_id}/acknowledge")
def acknowledge(request: Request, escalation_id: str, note: str = Form("")):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE sla_escalations SET status='Acknowledged', message=SUBSTR(message || ' | ACK: ' || :1,1,1000) WHERE escalation_id=:2 AND status='Open'",
                (note.strip()[:300] or user["user_id"], escalation_id))
    audit(conn, user, "SLA Escalation Acknowledged", escalation_id, note.strip()[:500])
    conn.commit(); conn.close()
    return RedirectResponse("/sla/escalation-history", status_code=303)


@router.post("/{escalation_id}/close")
def close(request: Request, escalation_id: str, note: str = Form(...)):
    user = current_user(request)
    if not allowed(user) or not note.strip():
        return RedirectResponse("/sla/escalation-history?msg=close-note-required", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE sla_escalations SET status='Closed', message=SUBSTR(message || ' | CLOSED: ' || :1,1,1000) WHERE escalation_id=:2 AND status IN ('Open','Acknowledged')",
                (note.strip()[:300], escalation_id))
    audit(conn, user, "SLA Escalation Closed", escalation_id, note.strip()[:500])
    conn.commit(); conn.close()
    return RedirectResponse("/sla/escalation-history", status_code=303)
