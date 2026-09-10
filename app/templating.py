"""Shared Jinja2Templates instance with app-wide globals registered.

All route modules import this single instance so every template can use the
RBAC helpers (`module_access`, `module_level`) without each route having to
pass them in the context.
"""

from datetime import datetime

from fastapi.templating import Jinja2Templates

from .auth import module_access, module_level, nav_levels
from .audit import _parse_oracle_dt

templates = Jinja2Templates(directory="app/templates")
templates.env.globals["module_access"] = module_access
templates.env.globals["module_level"] = module_level
templates.env.globals["nav_levels"] = nav_levels


def tenant_branding(user):
    defaults = {"name": "RentaGO", "logo": "/static/img/rentago-icon.svg",
                "favicon": "/static/img/rentago-icon.svg", "primary": "#16386E",
                "secondary": "#0d6efd"}
    tenant_id = (user or {}).get("tenant_id")
    if not tenant_id:
        return defaults
    try:
        from .db import get_connection
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SELECT display_name,logo_url,favicon_url,primary_color,secondary_color FROM tenants WHERE tenant_id=:1", (tenant_id,))
        row = cur.fetchone(); conn.close()
        if not row:
            return defaults
        return {"name": row[0] or defaults["name"], "logo": row[1] or defaults["logo"],
                "favicon": row[2] or defaults["favicon"], "primary": row[3] or defaults["primary"],
                "secondary": row[4] or defaults["secondary"]}
    except Exception:
        return defaults


templates.env.globals["tenant_branding"] = tenant_branding


def iso_date(value):
    """Normalize a date value (Oracle string, legacy DD-MM-YYYY, date) to
    YYYY-MM-DD so <input type="date"> calendars display it correctly."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    for fmt in ("%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y", "%d-%m-%Y",
                "%d/%m/%Y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return ""


templates.env.filters["iso_date"] = iso_date


def iso_dt(value):
    """Normalize a timestamp (Oracle string or ISO) to YYYY-MM-DDTHH:MM for
    <input type="datetime-local"> calendar+time prefill."""
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%dT%H:%M")
    dt = _parse_oracle_dt(value)
    if dt is None:
        for fmt in ("%Y-%m-%dT%H:%M", "%d-%m-%Y %H:%M"):
            try:
                from datetime import datetime as _d
                dt = _d.strptime(str(value).strip(), fmt)
                break
            except Exception:
                continue
    if dt is None:
        d = iso_date(value)
        return (d + "T00:00") if d else ""
    return dt.strftime("%Y-%m-%dT%H:%M")


templates.env.filters["iso_dt"] = iso_dt


def hour_minute(value):
    """Render login/logout timestamps as HH:MM for attendance logs."""
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    dt = _parse_oracle_dt(value)
    return dt.strftime("%H:%M") if dt else str(value)


templates.env.filters["hour_minute"] = hour_minute


def duration_hm(value):
    """Render stored decimal hours as elapsed HH:MM."""
    try:
        total_minutes = max(0, round(float(value or 0) * 60))
    except (TypeError, ValueError):
        return str(value or "")
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


templates.env.filters["duration_hm"] = duration_hm
