"""Tenant-admin profile and white-label settings foundation."""

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..auth import current_user
from ..db import get_connection
from ..templating import templates
from ..audit import audit
from ..tenant_context import current_tenant

router = APIRouter(prefix="/tenant/settings")


def tenant_admin(context):
    return context and context.membership_role.upper() in ("TENANT_ADMIN", "TENANT_OWNER")


@router.get("")
def settings_page(request: Request):
    user = current_user(request); context = current_tenant(request)
    if not user or not tenant_admin(context):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT tenant_id,tenant_code,legal_name,display_name,status,timezone,currency,logo_url,favicon_url,primary_color,secondary_color,domain,subdomain FROM tenants WHERE tenant_id=:1", (context.tenant_id,))
    row = cur.fetchone(); conn.close()
    tenant = dict(zip(("tenant_id", "code", "legal_name", "display_name", "status", "timezone", "currency", "logo_url", "favicon_url", "primary_color", "secondary_color", "domain", "subdomain"), row))
    return templates.TemplateResponse("tenant/settings.html", {"request": request, "user": user, "tenant": tenant})


@router.post("")
def update_settings(request: Request, display_name: str = Form(...), timezone: str = Form("Asia/Kolkata"),
                    currency: str = Form("INR"), logo_url: str = Form(""), favicon_url: str = Form(""),
                    primary_color: str = Form(""), secondary_color: str = Form("")):
    user = current_user(request); context = current_tenant(request)
    if not user or not tenant_admin(context):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "UPDATE tenants SET display_name=:1,timezone=:2,currency=:3,logo_url=:4,favicon_url=:5,primary_color=:6,secondary_color=:7,updated_at=SYSTIMESTAMP WHERE tenant_id=:8",
        (display_name.strip()[:200], timezone.strip()[:80], currency.strip()[:10], logo_url.strip()[:1000] or None,
         favicon_url.strip()[:1000] or None, primary_color.strip()[:20] or None, secondary_color.strip()[:20] or None, context.tenant_id),
    )
    audit(conn, user, "UPDATE_TENANT_SETTINGS", context.tenant_id, "Tenant branding/settings updated")
    conn.commit(); conn.close()
    return RedirectResponse("/tenant/settings", status_code=303)
