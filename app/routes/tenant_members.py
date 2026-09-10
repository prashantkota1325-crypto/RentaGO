"""Tenant-scoped membership administration."""

import uuid

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..auth import current_user
from ..db import get_connection
from ..templating import templates
from ..audit import audit
from ..tenant_context import current_tenant

router = APIRouter(prefix="/tenant/members")


def tenant_admin(context):
    return context and context.membership_role.upper() in ("TENANT_ADMIN", "TENANT_OWNER")


@router.get("")
def members(request: Request):
    user = current_user(request); context = current_tenant(request)
    if not user or not tenant_admin(context):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "SELECT m.membership_id,m.user_id,m.membership_role,m.status,u.name,u.email,u.role "
        "FROM tenant_memberships m LEFT JOIN users u ON UPPER(u.user_id)=UPPER(m.user_id) "
        "WHERE m.tenant_id=:1 ORDER BY u.name,m.user_id", (context.tenant_id,))
    rows = [dict(zip(("membership_id", "user_id", "membership_role", "status", "name", "email", "platform_role"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("tenant/members.html", {"request": request, "user": user, "rows": rows, "tenant": context})


@router.post("")
def add_member(request: Request, user_id: str = Form(...), membership_role: str = Form("MEMBER")):
    user = current_user(request); context = current_tenant(request)
    if not user or not tenant_admin(context) or membership_role not in ("MEMBER", "TENANT_ADMIN"):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE UPPER(user_id)=UPPER(:1) AND status='Active'", (user_id.strip(),))
    if not cur.fetchone():
        conn.close(); return RedirectResponse("/tenant/members?msg=user-not-found", status_code=303)
    cur.execute("SELECT COUNT(1) FROM tenant_memberships WHERE tenant_id=:1 AND UPPER(user_id)=UPPER(:2)", (context.tenant_id, user_id.strip()))
    if int(cur.fetchone()[0] or 0):
        conn.close(); return RedirectResponse("/tenant/members?msg=already-member", status_code=303)
    cur.execute("INSERT INTO tenant_memberships (membership_id,tenant_id,user_id,membership_role) VALUES (:1,:2,:3,:4)",
                ("TM-" + uuid.uuid4().hex[:20], context.tenant_id, user_id.strip(), membership_role))
    audit(conn, user, "ADD_TENANT_MEMBER", context.tenant_id, f"user={user_id}; role={membership_role}")
    conn.commit(); conn.close()
    return RedirectResponse("/tenant/members", status_code=303)


@router.post("/{membership_id}/suspend")
def suspend_member(request: Request, membership_id: str):
    return _change_member_status(request, membership_id, "SUSPENDED")


@router.post("/{membership_id}/activate")
def activate_member(request: Request, membership_id: str):
    return _change_member_status(request, membership_id, "ACTIVE")


def _change_member_status(request, membership_id, status):
    user = current_user(request); context = current_tenant(request)
    if not user or not tenant_admin(context):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE tenant_memberships SET status=:1 WHERE membership_id=:2 AND tenant_id=:3", (status, membership_id, context.tenant_id))
    audit(conn, user, "UPDATE_TENANT_MEMBERSHIP", context.tenant_id, f"membership={membership_id}; status={status}")
    conn.commit(); conn.close()
    return RedirectResponse("/tenant/members", status_code=303)
