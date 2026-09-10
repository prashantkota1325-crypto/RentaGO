"""SLA governance audit review."""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates

router = APIRouter(prefix="/sla/audit")


@router.get("")
def audit_history(request: Request, q: str = ""):
    user = current_user(request)
    if not user or module_level(user, "SLA Dashboard") != "F":
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    sql = (
        "SELECT audit_date,audit_time,user_id,audit_user,action,record,notes FROM audit_log "
        "WHERE (UPPER(action) LIKE '%SLA%' OR UPPER(record) LIKE '%SLA%' OR UPPER(notes) LIKE '%SLA%')")
    params = []
    if q:
        params.append("%" + q.upper() + "%")
        sql += " AND (UPPER(action) LIKE :1 OR UPPER(record) LIKE :1 OR UPPER(notes) LIKE :1)"
    sql += " ORDER BY audit_date DESC,audit_time DESC FETCH FIRST 500 ROWS ONLY"
    cur.execute(sql, params or None)
    rows = [dict(zip(("date", "time", "user_id", "user", "action", "record", "notes"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("sla/audit.html", {"request": request, "user": user, "rows": rows, "query": q})
