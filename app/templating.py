"""Shared Jinja2Templates instance with app-wide globals registered.

All route modules import this single instance so every template can use the
RBAC helpers (`module_access`, `module_level`) without each route having to
pass them in the context.
"""

from datetime import date, datetime, time
import re

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

PRODUCT_BRANDING = {
    "name": "RentaGO® CRM",
    "creator": "Prashant Kota",
    "attribution": "Designed & Built by Prashant Kota",
    "company": "RentaGO Technologies Pvt. Ltd.",
    "copyright": "© 2026 RentaGO Technologies Pvt. Ltd.",
    "rights": "All Rights Reserved.",
}


def product_branding():
    return PRODUCT_BRANDING


templates.env.globals["product_branding"] = product_branding


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


def display_date(value):
    """Render booking dates consistently for users as DD-MM-YYYY."""
    if not value:
        return ""
    if hasattr(value, "strftime"):
        return value.strftime("%d-%m-%Y")
    s = iso_date(value)
    if not s:
        return str(value)
    return datetime.strptime(s, "%Y-%m-%d").strftime("%d-%m-%Y")


templates.env.filters["display_date"] = display_date


def display_time(value):
    """Render time values consistently as HH:MM:SS."""
    if not value:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%H:%M:%S")
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    text = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M", "%I:%M %p", "%I:%M:%S %p"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M:%S")
        except ValueError:
            continue
    return text


templates.env.filters["display_time"] = display_time


def system_display(value):
    """Format database date/timestamp values when templates render them raw."""
    if isinstance(value, datetime):
        return value.strftime("%d-%m-%Y %H:%M:%S")
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    text = str(value).strip() if isinstance(value, str) else None
    if text and re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return display_date(text)
    if text and re.fullmatch(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}", text):
        parsed = datetime.strptime(text.replace("T", " "), "%Y-%m-%d %H:%M:%S")
        return parsed.strftime("%d-%m-%Y %H:%M:%S")
    return value


templates.env.finalize = system_display


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


def duration_words(value):
    """Render decimal hours as an elapsed duration, not a decimal clock."""
    try:
        total_minutes = max(0, round(float(value or 0) * 60))
    except (TypeError, ValueError):
        return str(value or "")
    hours, minutes = divmod(total_minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hr" + ("s" if hours != 1 else ""))
    if minutes or not parts:
        parts.append(f"{minutes} min" + ("s" if minutes != 1 else ""))
    return " ".join(parts)


templates.env.filters["duration_words"] = duration_words


def duration_clock_words(value):
    """Render planned route H.MM values with minute carry (e.g. 3.70 -> 4 hrs 10 mins)."""
    try:
        raw = float(value or 0)
        hours = int(raw)
        minutes = round((raw - hours) * 100)
        hours += minutes // 60
        minutes %= 60
    except (TypeError, ValueError):
        return str(value or "")
    parts = []
    if hours:
        parts.append(f"{hours} hr" + ("s" if hours != 1 else ""))
    if minutes or not parts:
        parts.append(f"{minutes} min" + ("s" if minutes != 1 else ""))
    return " ".join(parts)


templates.env.filters["duration_clock_words"] = duration_clock_words


def meters_to_km(value):
    try:
        return f"{float(value) / 1000:.2f} km"
    except (TypeError, ValueError):
        return "-"


templates.env.filters["meters_to_km"] = meters_to_km
