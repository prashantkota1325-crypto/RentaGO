"""Configurable SLA notification rule administration."""

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
import uuid

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates
from ..audit import audit

router = APIRouter(prefix="/sla/notification-rules")


def allowed(user):
    return bool(user) and module_level(user, "SLA Dashboard") == "F"


@router.get("")
def notification_rules(request: Request):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT notification_rule_id,event_name,trigger_status,channels,recipient_roles,template_name,status FROM sla_notification_rules ORDER BY event_name")
    rows = [dict(zip(("rule_id", "event", "trigger", "channels", "roles", "template", "status"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("sla/notification_rules.html", {"request": request, "user": user, "rows": rows})


@router.post("")
def create_notification_rule(request: Request, event_name: str = Form(...),
                             trigger_status: str = Form(""), channels: str = Form(...),
                             recipient_roles: str = Form(""), template_name: str = Form("")):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    rule_id = "NTF-RULE-" + uuid.uuid4().hex[:16]
    cur.execute(
        "INSERT INTO sla_notification_rules (notification_rule_id,event_name,trigger_status,channels,recipient_roles,template_name,status,created_by) "
        "VALUES (:1,:2,:3,:4,:5,:6,'Draft',:7)",
        (rule_id, event_name.strip(), trigger_status.strip() or None, channels.strip(),
         recipient_roles.strip() or None, template_name.strip() or None, user["user_id"]),
    )
    audit(conn, user, "SLA Notification Rule Created", rule_id, event_name)
    conn.commit(); conn.close()
    return RedirectResponse("/sla/notification-rules", status_code=303)


@router.post("/{rule_id}/publish")
def publish_notification_rule(request: Request, rule_id: str):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT event_name, trigger_status FROM sla_notification_rules WHERE notification_rule_id=:1 AND status='Draft'", (rule_id,))
    row = cur.fetchone()
    if not row:
        conn.close(); return RedirectResponse("/sla/notification-rules?msg=not-found", status_code=303)
    cur.execute(
        "UPDATE sla_notification_rules SET status='Archived' WHERE event_name=:1 "
        "AND NVL(trigger_status,'-')=NVL(:2,'-') AND status='Published'",
        row,
    )
    cur.execute("UPDATE sla_notification_rules SET status='Published', approved_by=:1 WHERE notification_rule_id=:2", (user["user_id"], rule_id))
    audit(conn, user, "SLA Notification Rule Published", rule_id, row[0])
    conn.commit(); conn.close()
    return RedirectResponse("/sla/notification-rules", status_code=303)
