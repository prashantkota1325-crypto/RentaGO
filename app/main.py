"""
RentaGO Web - FastAPI application entrypoint.

Run:  uvicorn app.main:app --reload
"""

import asyncio
import socket

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from .config import settings, validate_settings
from .templating import templates
from .routes import auth as auth_routes
from .routes import bookings as booking_routes
from .routes import dashboards as dashboard_routes
from .routes import trips as trip_routes
from .routes import invoices as invoice_routes
from .routes import payments as payment_routes
from .routes import notifications as notification_routes
from .routes import masters as master_routes
from .routes import reports as report_routes
from .routes import track as track_routes
from .routes import feedback as feedback_routes
from .routes import mobile as mobile_routes
from .routes import maps as maps_routes
from .routes import sla_admin as sla_admin_routes
from .routes import policies as policies_routes
from .routes import rules as rules_routes
from .routes import sla_notifications as sla_notification_routes
from .routes import sla_calendar as sla_calendar_routes
from .routes import sla_reports as sla_reports_routes
from .routes import sla_escalations as sla_escalation_routes
from .routes import sla_exceptions as sla_exception_routes
from .routes import sla_approvals as sla_approval_routes
from .routes import sla_events as sla_event_routes
from .routes import sla_escalation_history as sla_escalation_history_routes
from .routes import sla_notification_queue as sla_notification_queue_routes
from .routes import sla_audit as sla_audit_routes
from .routes import platform_tenants as platform_tenant_routes
from .routes import tenant_settings as tenant_settings_routes
from .routes import platform_plans as platform_plans_routes
from .routes import tenant_members as tenant_members_routes

app = FastAPI(title=settings.APP_NAME)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_routes.router)
app.include_router(booking_routes.router)
app.include_router(dashboard_routes.router)
app.include_router(trip_routes.router)
app.include_router(invoice_routes.router)
app.include_router(payment_routes.router)
app.include_router(notification_routes.router)
app.include_router(master_routes.router)
app.include_router(report_routes.router)
app.include_router(track_routes.router)
app.include_router(feedback_routes.router)
app.include_router(mobile_routes.router)
app.include_router(maps_routes.router)
app.include_router(sla_admin_routes.router)
app.include_router(policies_routes.router)
app.include_router(rules_routes.router)
app.include_router(sla_notification_routes.router)
app.include_router(sla_calendar_routes.router)
app.include_router(sla_reports_routes.router)
app.include_router(sla_escalation_routes.router)
app.include_router(sla_exception_routes.router)
app.include_router(sla_approval_routes.router)
app.include_router(sla_event_routes.router)
app.include_router(sla_escalation_history_routes.router)
app.include_router(sla_notification_queue_routes.router)
app.include_router(sla_audit_routes.router)
app.include_router(platform_tenant_routes.router)
app.include_router(tenant_settings_routes.router)
app.include_router(platform_plans_routes.router)
app.include_router(tenant_members_routes.router)


@app.on_event("startup")
async def start_background_sweeps():
    """Automatic GPS tracking sweep: driver T-2h / guest T-15min before
    pickup, one-tap tracking links are queued and positions auto-reported."""
    validate_settings()
    from .tracking import sweep_loop
    asyncio.create_task(sweep_loop())
    from .sla_worker import sweep_loop as sla_sweep_loop
    asyncio.create_task(sla_sweep_loop())
    from .notification_worker import delivery_loop
    asyncio.create_task(delivery_loop())
    from .compliance_worker import compliance_loop
    asyncio.create_task(compliance_loop())


@app.middleware("http")
async def tenant_host_guard(request: Request, call_next):
    """Enforce configured custom-domain tenant ownership after authentication."""
    from .db import get_connection
    from .tenant_context import resolve_tenant_by_host, current_tenant
    conn = get_connection()
    try:
        host_tenant = resolve_tenant_by_host(conn, request.headers.get("host", ""))
    finally:
        conn.close()
    if host_tenant:
        request.state.host_tenant_id = host_tenant[0]
        from .auth import current_user
        user = current_user(request)
        if user and (user.get("role") or "").strip().lower() != "super admin":
            context = current_tenant(request)
            if not context or context.tenant_id != str(host_tenant[0]):
                return JSONResponse({"detail": "tenant domain access denied"}, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.middleware("http")
async def csrf_protection(request: Request, call_next):
    from .csrf import COOKIE_NAME, FIELD_NAME, new_token, valid
    unsafe = request.method in {"POST", "PUT", "PATCH", "DELETE"}
    exempt = (
        request.url.path in {"/auth/login", "/auth/corporate-login", "/auth/vendor-login",
                             "/auth/guest-login", "/auth/driver-login", "/auth/register",
                             "/auth/verify-otp", "/mobile/guest-login", "/mobile/driver-login"}
        or request.url.path.startswith("/track/")
    )
    session_present = bool(request.cookies.get("rentago_session"))
    if unsafe and session_present and not exempt:
        supplied = request.headers.get("X-CSRF-Token")
        if not supplied:
            try:
                body = await request.body()
                request._body = body
                form = await request.form()
                supplied = form.get(FIELD_NAME)
            except Exception:
                supplied = None
        if not valid(request.cookies.get(COOKIE_NAME), supplied):
            return JSONResponse({"detail": "CSRF validation failed"}, status_code=403)
    response = await call_next(request)
    if not request.cookies.get(COOKIE_NAME):
        response.set_cookie(COOKIE_NAME, new_token(), httponly=False, secure=settings.SESSION_COOKIE_SECURE, samesite="lax")
    return response


@app.get("/")
def index():
    return RedirectResponse(url="/auth/login")


@app.get("/health", include_in_schema=False)
def health():
    """Minimal health endpoint for supervisors and external monitoring."""
    from .db import get_connection
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM dual")
        cur.fetchone()
        conn.close()
        return JSONResponse({"status": "ok", "database": "ok"})
    except Exception:
        return JSONResponse({"status": "degraded", "database": "unavailable"}, status_code=503)


@app.get("/health/db", include_in_schema=False)
def health_db():
    """Database-only health probe without exposing connection details."""
    return health()


@app.get("/ready", include_in_schema=False)
def ready():
    """Readiness probe: database and required core tables are available."""
    from .db import get_connection
    required = {"USERS", "BOOKINGS", "TRIPS", "INVOICES", "PAYMENTS", "NOTIFICATIONS"}
    try:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SELECT table_name FROM user_tables WHERE table_name IN ('USERS','BOOKINGS','TRIPS','INVOICES','PAYMENTS','NOTIFICATIONS')")
        present = {str(r[0]).upper() for r in cur.fetchall()}
        conn.close()
        if required - present:
            return JSONResponse({"status": "not_ready", "database": "ok"}, status_code=503)
        return JSONResponse({"status": "ready", "database": "ok"})
    except Exception:
        return JSONResponse({"status": "not_ready", "database": "unavailable"}, status_code=503)


@app.get("/health/workers", include_in_schema=False)
def health_workers():
    from .worker_status import snapshot
    workers = snapshot()
    expected = {"tracking", "sla", "notifications", "compliance"}
    missing = sorted(expected - set(workers))
    stale = sorted(name for name, data in workers.items() if data["status"] != "ok")
    status = "ok" if not missing and not stale else "degraded"
    return JSONResponse({"status": status, "workers": workers, "missing": missing, "stale": stale}, status_code=200 if status == "ok" else 503)


@app.get("/health/external-services", include_in_schema=False)
def health_external_services():
    """Configuration/network probe without credentials or provider messages."""
    smtp_dns = False
    try:
        socket.gethostbyname(settings.SMTP_HOST)
        smtp_dns = True
    except Exception:
        pass
    services = {
        "smtp": {"configured": bool(settings.SMTP_USER and settings.SMTP_PASSWORD), "dns": smtp_dns},
        "maps": {"configured": bool(settings.GOOGLE_MAPS_API_KEY or settings.MAPPLS_API_KEY), "provider": settings.MAP_PROVIDER},
        "whatsapp": {"configured": False, "mode": "manual wa.me links"},
        "sms": {"configured": False, "mode": "not configured"},
        "payment_gateway": {"configured": False, "mode": "application payment records"},
    }
    status = "ok" if services["smtp"]["configured"] and services["smtp"]["dns"] else "degraded"
    return JSONResponse({"status": status, "services": services}, status_code=200 if status == "ok" else 503)


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """Serve the service worker from the root scope so the app is installable
    (Add to Home Screen / Install app with the RentaGO logo)."""
    return FileResponse(
        "app/static/sw.js", media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


@app.get("/home")
def home(request: Request):
    # Require login
    from .auth import current_user
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    return templates.TemplateResponse(
        "home.html",
        {"request": request, "user": user, "app_name": settings.APP_NAME},
    )
