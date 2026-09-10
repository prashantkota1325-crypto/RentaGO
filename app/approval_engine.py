"""Configurable approval workflow primitives for SLA/policy actions."""

import uuid
from datetime import datetime


def request_approval(conn, workflow_id, entity_type, entity_id, requested_by):
    cur = conn.cursor()
    approval_id = f"APR-{uuid.uuid4().hex[:20]}"
    cur.execute(
        "INSERT INTO sla_approval_instances (approval_id, workflow_id, entity_type, entity_id, requested_by, requested_at) "
        "VALUES (:1,:2,:3,:4,:5,:6)",
        (approval_id, workflow_id, entity_type, str(entity_id), requested_by, datetime.now()),
    )
    return approval_id


def approve_step(conn, approval_id, approver_role):
    cur = conn.cursor()
    cur.execute("SELECT workflow_id, current_step, status FROM sla_approval_instances WHERE approval_id=:1", (approval_id,))
    row = cur.fetchone()
    if not row or row[2] != "Pending":
        raise ValueError("Approval is not pending")
    cur.execute(
        "SELECT approver_role FROM sla_approval_steps WHERE workflow_id=:1 AND step_no=:2 AND status='Active'",
        (row[0], row[1]),
    )
    step = cur.fetchone()
    if not step or str(step[0]).strip().lower() != str(approver_role).strip().lower():
        raise PermissionError("Approver role is not authorized for this step")
    cur.execute("SELECT COUNT(1) FROM sla_approval_steps WHERE workflow_id=:1 AND step_no>:2 AND status='Active'", (row[0], row[1]))
    if int(cur.fetchone()[0] or 0):
        cur.execute("UPDATE sla_approval_instances SET current_step=:1 WHERE approval_id=:2", (row[1] + 1, approval_id))
    else:
        cur.execute("UPDATE sla_approval_instances SET status='Approved', completed_at=:1 WHERE approval_id=:2", (datetime.now(), approval_id))
