"""Editable, versioned SLA definition administration."""

from datetime import datetime
import csv
import io

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, Response

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates
from ..audit import audit
from ..rule_engine import evaluate
from ..sla_engine import pause_instance, resume_instance

router = APIRouter(prefix="/sla")
PRIORITIES = ("P0", "P1", "P2", "P3")
STATUSES = ("Draft", "Published", "Archived")


def _admin(user):
    return bool(user) and module_level(user, "SLA Dashboard") == "F"


@router.get("/definitions")
def definitions(request: Request, status: str = ""):
    user = current_user(request)
    if not _admin(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    sql = "SELECT definition_id, sla_name, department, process_name, event_name, priority, duration_minutes, warning_percent, status, effective_from, effective_to, version, created_by, approved_by, change_reason FROM sla_definitions"
    params = []
    if status in STATUSES:
        sql += " WHERE status=:1"
        params.append(status)
    sql += " ORDER BY event_name, department, version DESC"
    cur.execute(sql, params or None)
    rows = [dict(zip(("definition_id", "sla_name", "department", "process_name", "event_name", "priority", "duration_minutes", "warning_percent", "status", "effective_from", "effective_to", "version", "created_by", "approved_by", "change_reason"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("sla/definitions.html", {"request": request, "user": user, "rows": rows, "statuses": STATUSES, "status_filter": status})


@router.get("/definitions/export")
def definitions_export(request: Request):
    user = current_user(request)
    if not _admin(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT definition_id, sla_name, department, process_name, event_name, priority, duration_minutes, warning_percent, status, effective_from, effective_to, version, created_by, approved_by, change_reason FROM sla_definitions ORDER BY event_name, department, version")
    buf = io.StringIO(); writer = csv.writer(buf)
    writer.writerow(["Definition ID", "SLA Name", "Department", "Process", "Event", "Priority", "Duration Minutes", "Warning Percent", "Status", "Effective From", "Effective To", "Version", "Created By", "Approved By", "Change Reason"])
    writer.writerows(cur.fetchall())
    audit(conn, user, "SLA Definitions Exported", "SLA Definitions", "")
    conn.commit(); conn.close()
    return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="rentago-sla-definitions.csv"'})


@router.post("/definitions/import")
def definitions_import(request: Request, file: UploadFile = File(...)):
    user = current_user(request)
    if not _admin(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    required = {"SLA Name", "Department", "Event", "Priority", "Duration Minutes", "Warning Percent"}
    try:
        text = file.file.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("missing required CSV columns")
        rows = list(reader)
        if not rows or len(rows) > 5000:
            raise ValueError("CSV must contain between 1 and 5000 rows")
        conn = get_connection(); cur = conn.cursor()
        for row in rows:
            priority = (row.get("Priority") or "P2").strip().upper()
            department = (row.get("Department") or "").strip()
            event_name = (row.get("Event") or "").strip()
            duration = int(row.get("Duration Minutes") or 0)
            warning = float(row.get("Warning Percent") or 75)
            if not department or not event_name or priority not in PRIORITIES or duration <= 0 or not 0 <= warning <= 100:
                raise ValueError("invalid department, event, priority, duration, or warning percent")
            cur.execute("SELECT NVL(MAX(version),0)+1 FROM sla_definitions WHERE event_name=:1 AND department=:2", (event_name, department))
            version = int(cur.fetchone()[0])
            definition_id = f"SLA-{event_name[:12].upper()}-{datetime.now():%Y%m%d%H%M%S%f}"[:40]
            cur.execute(
                "INSERT INTO sla_definitions (definition_id,sla_name,department,process_name,event_name,priority,duration_minutes,warning_percent,status,effective_from,version,created_by,change_reason) "
                "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,'Draft',SYSDATE,:9,:10,:11)",
                (definition_id, (row.get("SLA Name") or "").strip()[:200], department,
                 (row.get("Process") or "").strip()[:160] or None, event_name, priority,
                 duration, warning, version, user["user_id"], "Imported CSV"),
            )
        audit(conn, user, "SLA Definitions Imported", "SLA Definitions", f"rows={len(rows)}")
        conn.commit(); conn.close()
    except Exception:
        if "conn" in locals():
            conn.rollback(); conn.close()
        return RedirectResponse("/sla/definitions?msg=import-error", status_code=303)
    return RedirectResponse("/sla/definitions?msg=imported", status_code=303)


@router.get("/definitions/new")
def definition_new(request: Request, source_id: str = ""):
    user = current_user(request)
    if not _admin(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    record = {}
    if source_id:
        conn = get_connection(); cur = conn.cursor()
        cur.execute("SELECT sla_name, department, process_name, event_name, priority, duration_minutes, warning_percent, change_reason FROM sla_definitions WHERE definition_id=:1", (source_id,))
        row = cur.fetchone(); conn.close()
        if row:
            record = dict(zip(("sla_name", "department", "process_name", "event_name", "priority", "duration_minutes", "warning_percent", "change_reason"), row))
    return templates.TemplateResponse("sla/definition_form.html", {"request": request, "user": user, "record": record, "source_id": source_id, "priorities": PRIORITIES})


@router.post("/definitions/save")
def definition_save(request: Request, sla_name: str = Form(...), department: str = Form(...),
                    process_name: str = Form(""), event_name: str = Form(...),
                    priority: str = Form("P2"), duration_minutes: int = Form(...),
                    warning_percent: float = Form(75), change_reason: str = Form(""),
                    source_id: str = Form("")):
    user = current_user(request)
    if not _admin(user) or priority not in PRIORITIES or duration_minutes <= 0:
        return RedirectResponse("/sla/definitions?msg=invalid", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    if source_id:
        cur.execute("SELECT NVL(MAX(version),0)+1 FROM sla_definitions WHERE event_name=:1 AND department=:2", (event_name, department))
        version = int(cur.fetchone()[0])
        definition_id = f"SLA-{event_name[:12].upper()}-{version}-{datetime.now():%H%M%S}"
    else:
        definition_id = f"SLA-{event_name[:12].upper()}-{datetime.now():%Y%m%d%H%M%S}"
        version = 1
    cur.execute(
        "INSERT INTO sla_definitions (definition_id,sla_name,department,process_name,event_name,priority,duration_minutes,warning_percent,status,effective_from,version,created_by,change_reason) "
        "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,'Draft',SYSDATE,:9,:10,:11)",
        (definition_id, sla_name.strip(), department.strip(), process_name.strip() or None,
         event_name.strip(), priority, duration_minutes, warning_percent, version,
         user["user_id"], change_reason.strip()[:1000] or None),
    )
    audit(conn, user, "SLA Definition Draft Created", definition_id, f"version={version}")
    conn.commit(); conn.close()
    return RedirectResponse("/sla/definitions?msg=draft-created", status_code=303)


@router.post("/definitions/{definition_id}/publish")
def publish_definition(request: Request, definition_id: str):
    user = current_user(request)
    if not _admin(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT event_name, department FROM sla_definitions WHERE definition_id=:1", (definition_id,))
    row = cur.fetchone()
    if not row:
        conn.close(); return RedirectResponse("/sla/definitions?msg=not-found", status_code=303)
    cur.execute("UPDATE sla_definitions SET status='Archived', effective_to=SYSDATE WHERE UPPER(event_name)=UPPER(:1) AND UPPER(department)=UPPER(:2) AND status='Published'", row)
    cur.execute("UPDATE sla_definitions SET status='Published', approved_by=:1, approved_dt=SYSDATE WHERE definition_id=:2", (user["user_id"], definition_id))
    audit(conn, user, "SLA Definition Published", definition_id, "")
    conn.commit(); conn.close()
    return RedirectResponse("/sla/definitions?msg=published", status_code=303)


@router.post("/instances/{instance_id}/pause")
def pause_sla(request: Request, instance_id: str, reason: str = Form(...)):
    user = current_user(request)
    if not _admin(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection()
    try:
        pause_instance(conn, instance_id, user["user_id"], reason)
        audit(conn, user, "SLA Paused", instance_id, reason[:500])
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        return RedirectResponse("/sla/definitions?msg=pause-error", status_code=303)
    conn.close()
    return RedirectResponse("/sla/definitions?msg=paused", status_code=303)


@router.post("/instances/{instance_id}/resume")
def resume_sla(request: Request, instance_id: str):
    user = current_user(request)
    if not _admin(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection()
    try:
        resume_instance(conn, instance_id, user["user_id"])
        audit(conn, user, "SLA Resumed", instance_id, "")
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        return RedirectResponse("/sla/definitions?msg=resume-error", status_code=303)
    conn.close()
    return RedirectResponse("/sla/definitions?msg=resumed", status_code=303)


@router.post("/instances/{instance_id}/resolve")
def resolve_sla(request: Request, instance_id: str, resolution_note: str = Form(...)):
    user = current_user(request)
    if not _admin(user) or not resolution_note.strip():
        return RedirectResponse("/sla/instances?msg=resolution-note-required", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT status FROM sla_instances WHERE instance_id=:1", (instance_id,))
    row = cur.fetchone()
    if not row or row[0] not in ("ACTIVE", "AT_RISK", "BREACHED", "PAUSED"):
        conn.close(); return RedirectResponse("/sla/instances?msg=not-resolvable", status_code=303)
    cur.execute("UPDATE sla_instances SET status='RESOLVED', completed_at=SYSDATE, resolution_note=:1 WHERE instance_id=:2",
                (resolution_note.strip()[:1000], instance_id))
    audit(conn, user, "SLA Instance Resolved", instance_id, resolution_note.strip()[:500])
    conn.commit(); conn.close()
    return RedirectResponse("/sla/instances?msg=resolved", status_code=303)


@router.post("/instances/{instance_id}/reopen")
def reopen_sla(request: Request, instance_id: str, reason: str = Form(...)):
    user = current_user(request)
    if not _admin(user) or not reason.strip():
        return RedirectResponse("/sla/instances?msg=reopen-reason-required", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE sla_instances SET status='ACTIVE', completed_at=NULL, resolution_note=:1 WHERE instance_id=:2 AND status='RESOLVED'",
                ("Reopened: " + reason.strip()[:950], instance_id))
    if cur.rowcount != 1:
        conn.close(); return RedirectResponse("/sla/instances?msg=not-reopenable", status_code=303)
    audit(conn, user, "SLA Instance Reopened", instance_id, reason.strip()[:500])
    conn.commit(); conn.close()
    return RedirectResponse("/sla/instances?msg=reopened", status_code=303)


@router.get("/simulator")
def sla_simulator(request: Request, event_name: str = "BOOKING_CREATED",
                  department: str = "Operations", priority: str = "P2",
                  context_json: str = "{}"):
    user = current_user(request)
    if not _admin(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    result = None
    try:
        import json
        context = json.loads(context_json or "{}")
        conn = get_connection(); cur = conn.cursor()
        cur.execute(
            "SELECT definition_id, sla_name, duration_minutes, priority FROM sla_definitions "
            "WHERE UPPER(event_name)=UPPER(:1) AND UPPER(department)=UPPER(:2) "
            "AND status='Published' ORDER BY version DESC FETCH FIRST 1 ROWS ONLY",
            (event_name, department))
        definition = cur.fetchone()
        context.setdefault("department", department)
        rules = evaluate(conn, event_name, context, department)
        conn.close()
        result = {"definition": definition, "rules": rules,
                  "effective_priority": rules["actions"].get("priority", definition[3] if definition else priority),
                  "effective_minutes": rules["actions"].get("duration_minutes", definition[2] if definition else None)}
    except Exception as exc:
        result = {"error": str(exc)}
    return templates.TemplateResponse("sla/simulator.html", {"request": request, "user": user,
        "event_name": event_name, "department": department, "priority": priority,
        "context_json": context_json, "result": result})


@router.get("/instances")
def sla_instances(request: Request, status: str = ""):
    user = current_user(request)
    if not _admin(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    sql = (
        "SELECT i.instance_id, i.entity_type, i.entity_id, i.department, i.priority, "
        "i.started_at, i.due_at, i.status, d.sla_name "
        "FROM sla_instances i JOIN sla_definitions d ON d.definition_id=i.definition_id"
    )
    params = []
    if status:
        sql += " WHERE i.status=:1"; params.append(status)
    sql += " ORDER BY i.due_at FETCH FIRST 500 ROWS ONLY"
    cur.execute(sql, params or None)
    rows = [dict(zip(("instance_id", "entity_type", "entity_id", "department", "priority", "started_at", "due_at", "status", "sla_name"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("sla/instances.html", {"request": request, "user": user, "rows": rows, "status_filter": status})
