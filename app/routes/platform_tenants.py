"""RentaGO platform-level tenant administration."""

import uuid

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..auth import current_user, is_platform_owner
from ..db import get_connection
from ..templating import templates
from ..audit import audit

router = APIRouter(prefix="/platform/tenants")


def super_admin(user):
    return is_platform_owner(user)


@router.get("")
def tenant_list(request: Request):
    user = current_user(request)
    if not super_admin(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "SELECT tenant_id,tenant_code,legal_name,display_name,status,plan_code,subscription_status,timezone,currency,created_at "
        "FROM tenants ORDER BY created_at DESC")
    rows = [dict(zip(("tenant_id", "code", "legal_name", "display_name", "status", "plan", "subscription", "timezone", "currency", "created_at"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("platform/tenants.html", {"request": request, "user": user, "rows": rows})


@router.post("")
def create_tenant(request: Request, tenant_code: str = Form(...), legal_name: str = Form(...),
                  display_name: str = Form(...), plan_code: str = Form("STARTER"),
                  timezone: str = Form("Asia/Kolkata"), currency: str = Form("INR")):
    user = current_user(request)
    if not super_admin(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    tenant_code = tenant_code.strip().upper()
    if not tenant_code or not legal_name.strip() or not display_name.strip():
        return RedirectResponse("/platform/tenants?msg=invalid", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    tenant_id = "TEN-" + uuid.uuid4().hex[:20].upper()
    cur.execute(
        "INSERT INTO tenants (tenant_id,tenant_code,legal_name,display_name,status,plan_code,subscription_status,timezone,currency) "
        "VALUES (:1,:2,:3,:4,'TRIAL',:5,'TRIAL',:6,:7)",
        (tenant_id, tenant_code[:60], legal_name.strip()[:200], display_name.strip()[:200], plan_code.strip()[:60], timezone.strip()[:80], currency.strip()[:10]),
    )
    audit(conn, user, "CREATE_TENANT", tenant_id, f"code={tenant_code}; plan={plan_code}")
    conn.commit(); conn.close()
    return RedirectResponse("/platform/tenants", status_code=303)


@router.post("/{tenant_id}/activate")
def activate_tenant(request: Request, tenant_id: str):
    return _change_status(request, tenant_id, "ACTIVE", "ACTIVATE_TENANT")


@router.post("/{tenant_id}/suspend")
def suspend_tenant(request: Request, tenant_id: str):
    return _change_status(request, tenant_id, "SUSPENDED", "SUSPEND_TENANT")


def _change_status(request, tenant_id, status, action):
    user = current_user(request)
    if not super_admin(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE tenants SET status=:1, updated_at=SYSTIMESTAMP, activated_at=CASE WHEN :1='ACTIVE' THEN SYSTIMESTAMP ELSE activated_at END, suspended_at=CASE WHEN :1='SUSPENDED' THEN SYSTIMESTAMP ELSE suspended_at END WHERE tenant_id=:2", (status, tenant_id))
    audit(conn, user, action, tenant_id, f"status={status}")
    conn.commit(); conn.close()
    return RedirectResponse("/platform/tenants", status_code=303)
