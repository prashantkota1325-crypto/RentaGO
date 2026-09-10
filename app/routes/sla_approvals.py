"""SLA approval workflow and ordered step administration."""

import uuid

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates
from ..audit import audit

router = APIRouter(prefix="/sla/approvals")


def allowed(user):
    return bool(user) and module_level(user, "SLA Dashboard") == "F"


@router.get("")
def workflows(request: Request):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "SELECT w.workflow_id,w.workflow_name,w.department,w.event_name,w.approval_mode,w.status,w.version, "
        "(SELECT COUNT(1) FROM sla_approval_steps s WHERE s.workflow_id=w.workflow_id AND s.status='Active') "
        "FROM sla_approval_workflows w ORDER BY w.workflow_name,w.version DESC")
    rows = [dict(zip(("workflow_id", "name", "department", "event", "mode", "status", "version", "steps"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("sla/approvals.html", {"request": request, "user": user, "rows": rows})


@router.post("")
def create_workflow(request: Request, workflow_name: str = Form(...), department: str = Form(""),
                    event_name: str = Form(""), approval_mode: str = Form("SEQUENTIAL")):
    user = current_user(request)
    if not allowed(user) or approval_mode not in ("SEQUENTIAL", "ANY"):
        return RedirectResponse("/sla/approvals?msg=invalid", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    workflow_id = "WF-" + uuid.uuid4().hex[:20]
    cur.execute(
        "INSERT INTO sla_approval_workflows (workflow_id,workflow_name,department,event_name,approval_mode,status,created_by) "
        "VALUES (:1,:2,:3,:4,:5,'Draft',:6)",
        (workflow_id, workflow_name.strip()[:200], department.strip() or None,
         event_name.strip() or None, approval_mode, user["user_id"]),
    )
    audit(conn, user, "SLA Approval Workflow Created", workflow_id, workflow_name)
    conn.commit(); conn.close()
    return RedirectResponse("/sla/approvals", status_code=303)


@router.post("/{workflow_id}/steps")
def add_step(request: Request, workflow_id: str, approver_role: str = Form(...),
             approval_condition: str = Form("")):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT status FROM sla_approval_workflows WHERE workflow_id=:1", (workflow_id,))
    workflow = cur.fetchone()
    if not workflow or workflow[0] != "Draft":
        conn.close(); return RedirectResponse("/sla/approvals?msg=workflow-locked", status_code=303)
    cur.execute("SELECT NVL(MAX(step_no),0)+1 FROM sla_approval_steps WHERE workflow_id=:1", (workflow_id,))
    step_no = int(cur.fetchone()[0])
    step_id = "WFSTEP-" + uuid.uuid4().hex[:20]
    cur.execute(
        "INSERT INTO sla_approval_steps (step_id,workflow_id,step_no,approver_role,approval_condition,status) "
        "VALUES (:1,:2,:3,:4,:5,'Active')",
        (step_id, workflow_id, step_no, approver_role.strip()[:100], approval_condition.strip()[:1000] or None),
    )
    audit(conn, user, "SLA Approval Step Added", workflow_id, f"step={step_no} role={approver_role}")
    conn.commit(); conn.close()
    return RedirectResponse("/sla/approvals", status_code=303)


@router.post("/{workflow_id}/publish")
def publish_workflow(request: Request, workflow_id: str):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT COUNT(1) FROM sla_approval_steps WHERE workflow_id=:1 AND status='Active'", (workflow_id,))
    if int(cur.fetchone()[0] or 0) == 0:
        conn.close(); return RedirectResponse("/sla/approvals?msg=steps-required", status_code=303)
    cur.execute("UPDATE sla_approval_workflows SET status='Published', approved_by=:1 WHERE workflow_id=:2 AND status='Draft'", (user["user_id"], workflow_id))
    audit(conn, user, "SLA Approval Workflow Published", workflow_id, "")
    conn.commit(); conn.close()
    return RedirectResponse("/sla/approvals", status_code=303)
