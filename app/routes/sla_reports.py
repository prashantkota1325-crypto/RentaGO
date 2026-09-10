"""SLA compliance scorecards and management reporting."""

from datetime import datetime
import csv
import io

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates
from ..audit import audit
from ..audit import _parse_oracle_dt

router = APIRouter(prefix="/sla/reports")


def _allowed(user):
    return bool(user) and module_level(user, "SLA Dashboard") is not None


def _data(cur):
    cur.execute("SELECT department, status, started_at, completed_at FROM sla_instances")
    grouped = {}
    for department, status, started, completed in cur.fetchall():
        key = department or "Unassigned"
        row = grouped.setdefault(key, {"department": key, "total": 0, "active": 0,
                                       "at_risk": 0, "breached": 0, "resolved": 0,
                                       "completed_minutes": []})
        row["total"] += 1
        status = str(status or "ACTIVE").upper()
        if status == "ACTIVE": row["active"] += 1
        elif status == "AT_RISK": row["at_risk"] += 1
        elif status == "BREACHED": row["breached"] += 1
        elif status in ("RESOLVED", "COMPLETED"): row["resolved"] += 1
        started_dt = _parse_oracle_dt(started)
        completed_dt = _parse_oracle_dt(completed)
        if started_dt and completed_dt:
            row["completed_minutes"].append((completed_dt - started_dt).total_seconds() / 60)
    output = []
    for row in grouped.values():
        closed = row["resolved"] + row["breached"]
        row["compliance"] = round(row["resolved"] / closed * 100, 1) if closed else 100.0
        values = row.pop("completed_minutes")
        row["average_minutes"] = round(sum(values) / len(values), 1) if values else 0
        output.append(row)
    return sorted(output, key=lambda x: x["department"])


@router.get("")
def sla_report(request: Request, export: str = ""):
    user = current_user(request)
    if not _allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    rows = _data(cur)
    audit(conn, user, "SLA Scorecard Exported" if export else "SLA Scorecard Viewed", "SLA", f"departments={len(rows)}")
    conn.commit(); conn.close()
    if export:
        buf = io.StringIO(); writer = csv.DictWriter(buf, fieldnames=("department", "total", "active", "at_risk", "breached", "resolved", "compliance", "average_minutes")); writer.writeheader(); writer.writerows(rows)
        return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="rentago-sla-scorecard.csv"'})
    return templates.TemplateResponse("sla/scorecard.html", {"request": request, "user": user, "rows": rows})


@router.get("/instances")
def instance_report(request: Request, status: str = "", department: str = "", export: str = ""):
    user = current_user(request)
    if not _allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    sql = (
        "SELECT i.instance_id,d.sla_name,d.event_name,i.entity_type,i.entity_id,i.department,i.priority, "
        "i.started_at,i.due_at,i.completed_at,i.status,i.resolution_note, "
        "(SELECT COUNT(1) FROM sla_escalations e WHERE e.instance_id=i.instance_id), "
        "(SELECT COUNT(1) FROM sla_exceptions x WHERE x.instance_id=i.instance_id AND x.status='Approved') "
        "FROM sla_instances i JOIN sla_definitions d ON d.definition_id=i.definition_id")
    params = []; where = []
    if status:
        params.append(status.upper()); where.append(f"i.status=:{len(params)}")
    if department:
        params.append(department); where.append(f"UPPER(i.department)=UPPER(:{len(params)})")
    if where: sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY i.due_at FETCH FIRST 1000 ROWS ONLY"
    cur.execute(sql, params or None)
    now = datetime.now()
    rows = []
    for row in cur.fetchall():
        started = _parse_oracle_dt(row[7]); due = _parse_oracle_dt(row[8]); completed = _parse_oracle_dt(row[9])
        end = completed or now
        age = round(max(0, (end - started).total_seconds() / 60), 1) if started else 0
        overdue = round(max(0, (now - due).total_seconds() / 60), 1) if due and not completed else 0
        rows.append({"instance_id": row[0], "sla_name": row[1], "event": row[2], "entity_type": row[3], "entity_id": row[4],
                     "department": row[5], "priority": row[6], "started": started, "due": due, "completed": completed,
                     "status": row[10], "age_minutes": age, "overdue_minutes": overdue, "escalations": row[12],
                     "exception": "Yes" if row[13] else "No", "resolution": row[11] or ""})
    audit(conn, user, "SLA Instance Report Exported" if export else "SLA Instance Report Viewed", "SLA", f"rows={len(rows)}")
    conn.commit(); conn.close()
    if export:
        fields = ("instance_id", "sla_name", "event", "entity_type", "entity_id", "department", "priority", "started", "due", "completed", "status", "age_minutes", "overdue_minutes", "escalations", "exception", "resolution")
        buf = io.StringIO(); writer = csv.DictWriter(buf, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
        return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="rentago-sla-instances.csv"'})
    return templates.TemplateResponse("sla/instance_report.html", {"request": request, "user": user, "rows": rows, "status_filter": status, "department_filter": department})
