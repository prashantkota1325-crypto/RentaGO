"""Configurable multi-level SLA escalation administration."""

import uuid

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates
from ..audit import audit

router = APIRouter(prefix="/sla/escalations")


def allowed(user):
    return bool(user) and module_level(user, "SLA Dashboard") == "F"


@router.get("")
def escalation_rules(request: Request):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "SELECT rule_id,event_name,department,priority,escalation_level,trigger_percent,channels,recipient_roles,status "
        "FROM sla_escalation_rules ORDER BY event_name, department, escalation_level")
    rows = [dict(zip(("rule_id", "event", "department", "priority", "level", "trigger", "channels", "roles", "status"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("sla/escalations.html", {"request": request, "user": user, "rows": rows})


@router.post("")
def create_escalation_rule(request: Request, event_name: str = Form(...), department: str = Form(""),
                           priority: str = Form(""), escalation_level: int = Form(...),
                           trigger_percent: float = Form(...), channels: str = Form("email"),
                           recipient_roles: str = Form("")):
    user = current_user(request)
    if not allowed(user) or escalation_level < 1 or escalation_level > 9 or trigger_percent < 0:
        return RedirectResponse("/sla/escalations?msg=invalid", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    rule_id = "ESC-RULE-" + uuid.uuid4().hex[:20]
    cur.execute(
        "INSERT INTO sla_escalation_rules (rule_id,event_name,department,priority,escalation_level,trigger_percent,channels,recipient_roles,status,created_by) "
        "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,'Draft',:9)",
        (rule_id, event_name.strip(), department.strip() or None, priority.strip().upper() or None,
         escalation_level, trigger_percent, channels.strip() or None, recipient_roles.strip() or None,
         user["user_id"]),
    )
    audit(conn, user, "SLA Escalation Rule Created", rule_id, event_name)
    conn.commit(); conn.close()
    return RedirectResponse("/sla/escalations", status_code=303)


@router.post("/{rule_id}/publish")
def publish_escalation_rule(request: Request, rule_id: str):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE sla_escalation_rules SET status='Published', approved_by=:1 WHERE rule_id=:2", (user["user_id"], rule_id))
    audit(conn, user, "SLA Escalation Rule Published", rule_id, "")
    conn.commit(); conn.close()
    return RedirectResponse("/sla/escalations", status_code=303)
