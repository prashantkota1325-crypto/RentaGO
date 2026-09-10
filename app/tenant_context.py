"""Canonical tenant context foundation for the SaaS migration."""

from dataclasses import dataclass

from fastapi import HTTPException, Request

from .auth import current_user
from .db import get_connection


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    tenant_code: str
    display_name: str
    membership_role: str
    user_id: str


class TenantContextError(RuntimeError):
    pass


def select_membership(rows, user_id):
    """Select one active membership; ambiguity fails closed."""
    active = [r for r in rows if str(r[3] or "").upper() == "ACTIVE"]
    if len(active) != 1:
        raise TenantContextError("tenant context is missing or ambiguous")
    tenant_id, tenant_code, display_name, status, role = active[0]
    return TenantContext(str(tenant_id), str(tenant_code), str(display_name), str(role), str(user_id))


def current_tenant(request: Request) -> TenantContext | None:
    user = current_user(request)
    if not user:
        return None
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "SELECT t.tenant_id,t.tenant_code,t.display_name,m.status,m.membership_role "
        "FROM tenant_memberships m JOIN tenants t ON t.tenant_id=m.tenant_id "
        "WHERE UPPER(m.user_id)=UPPER(:1) AND m.status='ACTIVE' AND t.status IN ('TRIAL','ACTIVE','PAST_DUE')",
        (user["user_id"],),
    )
    rows = cur.fetchall(); conn.close()
    return select_membership(rows, user["user_id"])


def require_tenant(request: Request) -> TenantContext:
    context = current_tenant(request)
    if context is None:
        raise HTTPException(status_code=403, detail="tenant context required")
    return context


def resolve_tenant_by_host(conn, host):
    """Resolve a configured tenant domain/subdomain; never grants access alone."""
    hostname = (host or "").split(":", 1)[0].strip().lower()
    cur = conn.cursor()
    cur.execute(
        "SELECT tenant_id,tenant_code,display_name,status FROM tenants "
        "WHERE LOWER(domain)=:1 OR LOWER(subdomain)=:1", (hostname,))
    row = cur.fetchone()
    return row
