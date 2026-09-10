"""SLA event-ledger administration."""

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response
import csv
import io

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates

router = APIRouter(prefix="/sla/events")


@router.get("")
def event_history(request: Request, outcome: str = "", export: str = ""):
    user = current_user(request)
    if not user or module_level(user, "SLA Dashboard") != "F":
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    sql = "SELECT event_id,source_event_id,event_name,entity_type,entity_id,department,outcome,instance_id,error_message,created_dt FROM sla_event_log"
    params = []
    if outcome:
        sql += " WHERE outcome=:1"; params.append(outcome)
    sql += " ORDER BY created_dt DESC FETCH FIRST 500 ROWS ONLY"
    cur.execute(sql, params or None)
    rows = [dict(zip(("event_id", "source_event_id", "event", "entity_type", "entity_id", "department", "outcome", "instance_id", "error", "created_dt"), r)) for r in cur.fetchall()]
    if export:
        buf = io.StringIO(); writer = csv.DictWriter(buf, fieldnames=tuple(rows[0].keys()) if rows else ("event_id", "source_event_id", "event", "entity_type", "entity_id", "department", "outcome", "instance_id", "error", "created_dt")); writer.writeheader(); writer.writerows(rows)
        conn.close()
        return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="rentago-sla-events.csv"'})
    conn.close()
    return templates.TemplateResponse("sla/events.html", {"request": request, "user": user, "rows": rows, "outcome_filter": outcome})
