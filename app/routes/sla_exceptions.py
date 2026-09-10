"""SLA exception requests backed by the configurable approval engine."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates
from ..audit import audit
from ..approval_engine import request_approval, approve_step

router = APIRouter(prefix="/sla/exceptions")


def allowed(user):
    return bool(user) and module_level(user, "SLA Dashboard") == "F"


@router.get("")
def exceptions(request: Request):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "SELECT e.exception_id,e.instance_id,e.category,e.reason,e.created_by,e.created_at,e.status,e.approved_by, "
        "a.approval_id,a.status,a.current_step FROM sla_exceptions e "
        "LEFT JOIN sla_approval_instances a ON a.entity_type='SLA_EXCEPTION' AND a.entity_id=e.exception_id "
        "ORDER BY e.created_at DESC")
    rows = [dict(zip(("exception_id", "instance_id", "category", "reason", "created_by", "created_at", "status", "approved_by", "approval_id", "approval_status", "current_step"), r)) for r in cur.fetchall()]
    cur.execute("SELECT workflow_id, workflow_name FROM sla_approval_workflows WHERE status='Published' ORDER BY workflow_name")
    workflows = [{"id": r[0], "name": r[1]} for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("sla/exceptions.html", {"request": request, "user": user, "rows": rows, "workflows": workflows})


@router.post("")
def request_exception(request: Request, instance_id: str = Form(...), category: str = Form(...),
                      reason: str = Form(...), workflow_id: str = Form(...)):
    user = current_user(request)
    if not allowed(user) or not reason.strip() or not category.strip():
        return RedirectResponse("/sla/exceptions?msg=invalid", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT instance_id FROM sla_instances WHERE instance_id=:1", (instance_id,))
    if not cur.fetchone():
        conn.close(); return RedirectResponse("/sla/exceptions?msg=instance-not-found", status_code=303)
    cur.execute("SELECT workflow_id FROM sla_approval_workflows WHERE workflow_id=:1 AND status='Published'", (workflow_id,))
    if not cur.fetchone():
        conn.close(); return RedirectResponse("/sla/exceptions?msg=workflow-not-published", status_code=303)
    exception_id = "EXC-" + uuid.uuid4().hex[:20]
    cur.execute(
        "INSERT INTO sla_exceptions (exception_id,instance_id,category,reason,created_by,created_at,status) "
        "VALUES (:1,:2,:3,:4,:5,:6,'Pending')",
        (exception_id, instance_id, category.strip()[:120], reason.strip()[:1000], user["user_id"], datetime.now()),
    )
    approval_id = request_approval(conn, workflow_id, "SLA_EXCEPTION", exception_id, user["user_id"])
    audit(conn, user, "SLA Exception Requested", exception_id, f"approval={approval_id}")
    conn.commit(); conn.close()
    return RedirectResponse("/sla/exceptions", status_code=303)


@router.post("/{exception_id}/approve")
def approve_exception(request: Request, exception_id: str):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT approval_id FROM sla_approval_instances WHERE entity_type='SLA_EXCEPTION' AND entity_id=:1", (exception_id,))
    row = cur.fetchone()
    if not row:
        conn.close(); return RedirectResponse("/sla/exceptions?msg=approval-not-found", status_code=303)
    try:
        approve_step(conn, row[0], user.get("role", ""))
        cur.execute("SELECT status FROM sla_approval_instances WHERE approval_id=:1", (row[0],))
        status = cur.fetchone()[0]
        if status == "Approved":
            cur.execute("UPDATE sla_exceptions SET status='Approved', approved_by=:1, approved_at=SYSDATE WHERE exception_id=:2", (user["user_id"], exception_id))
        audit(conn, user, "SLA Exception Approval Step", exception_id, f"approval={row[0]} status={status}")
        conn.commit()
    except Exception:
        conn.rollback()
    conn.close()
    return RedirectResponse("/sla/exceptions", status_code=303)


@router.post("/{exception_id}/reject")
def reject_exception(request: Request, exception_id: str):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE sla_exceptions SET status='Rejected', approved_by=:1, approved_at=SYSDATE WHERE exception_id=:2 AND status='Pending'", (user["user_id"], exception_id))
    cur.execute("UPDATE sla_approval_instances SET status='Rejected', completed_at=SYSDATE WHERE entity_type='SLA_EXCEPTION' AND entity_id=:1 AND status='Pending'", (exception_id,))
    audit(conn, user, "SLA Exception Rejected", exception_id, "")
    conn.commit(); conn.close()
    return RedirectResponse("/sla/exceptions", status_code=303)
