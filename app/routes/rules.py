"""Internal business-rule administration."""

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse
import uuid
import json
import csv
import io
from fastapi.responses import Response

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates
from ..audit import audit

router = APIRouter(prefix="/rules")


def allowed(user):
    return bool(user) and module_level(user, "Policies") == "F"


@router.get("")
def rule_list(request: Request):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT rule_id, rule_name, event_name, department, scope_type, scope_value, priority, status, version FROM business_rules ORDER BY rule_name")
    rows = [dict(zip(("rule_id", "rule_name", "event_name", "department", "scope_type", "scope_value", "priority", "status", "version"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("rules/list.html", {"request": request, "user": user, "rows": rows})


@router.get("/export")
def rule_export(request: Request):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT rule_id,rule_name,event_name,department,scope_type,scope_value,priority,condition_definition,action_definition,status,version FROM business_rules ORDER BY rule_name,version DESC")
    buf = io.StringIO(); writer = csv.writer(buf)
    writer.writerow(["Rule ID", "Rule Name", "Event", "Department", "Scope Type", "Scope Value", "Priority", "Conditions JSON", "Actions JSON", "Status", "Version"])
    writer.writerows(cur.fetchall())
    audit(conn, user, "Business Rule Configuration Exported", "Business Rules", "")
    conn.commit(); conn.close()
    return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="rentago-business-rules.csv"'})


@router.post("/import")
def rule_import(request: Request, file: UploadFile = File(...)):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    try:
        reader = csv.DictReader(io.StringIO(file.file.read().decode("utf-8-sig")))
        required = {"Rule Name", "Event", "Conditions JSON", "Actions JSON"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("missing CSV columns")
        count = 0
        for row in list(reader)[:5000]:
            conditions = json_object(row.get("Conditions JSON"), "Conditions")
            actions = json_object(row.get("Actions JSON"), "Actions")
            cur.execute(
                "INSERT INTO business_rules (rule_id,rule_name,event_name,department,scope_type,scope_value,priority,condition_definition,action_definition,status,version,created_by) "
                "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,'Draft',1,:10)",
                ("RULE-" + uuid.uuid4().hex[:20], (row.get("Rule Name") or "Imported")[:200],
                 (row.get("Event") or "").strip(), (row.get("Department") or "").strip() or None,
                 (row.get("Scope Type") or "").strip() or None, (row.get("Scope Value") or "").strip() or None,
                 (row.get("Priority") or "P2").strip(), conditions, actions, user["user_id"]),
            )
            count += 1
        audit(conn, user, "Business Rule Configuration Imported", "Business Rules", f"rows={count}")
        conn.commit()
    except Exception:
        conn.rollback(); conn.close()
        return RedirectResponse("/rules?msg=import-error", status_code=303)
    conn.close()
    return RedirectResponse("/rules?msg=imported", status_code=303)


@router.get("/new")
def rule_new(request: Request):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    return templates.TemplateResponse("rules/form.html", {"request": request, "user": user})


@router.post("/new")
def rule_create(request: Request, rule_name: str = Form(...), event_name: str = Form(...),
                department: str = Form(""), priority: str = Form("P2"),
                scope_type: str = Form(""), scope_value: str = Form(""),
                conditions: str = Form("{}"), actions: str = Form("{}")):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    rule_id = "RULE-" + uuid.uuid4().hex[:20]
    scopes = ("", "department", "process", "service", "corporate", "vendor", "contract", "transaction")
    scope_type = scope_type.strip().lower()
    if scope_type not in scopes:
        return RedirectResponse("/rules?msg=invalid-scope", status_code=303)
    cur.execute(
        "INSERT INTO business_rules (rule_id,rule_name,event_name,department,scope_type,scope_value,priority,condition_definition,action_definition,status,created_by) "
        "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,'Draft',:10)",
        (rule_id, rule_name.strip(), event_name.strip(), department.strip() or None,
          scope_type or None, scope_value.strip()[:160] or None, priority, conditions, actions, user["user_id"]),
    )
    audit(conn, user, "Business Rule Draft Created", rule_id, rule_name)
    conn.commit(); conn.close()
    return RedirectResponse("/rules?msg=created", status_code=303)


@router.post("/{rule_id}/publish")
def rule_publish(request: Request, rule_id: str):
    user = current_user(request)
    if not allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("UPDATE business_rules SET status='Published', approved_by=:1 WHERE rule_id=:2", (user["user_id"], rule_id))
    audit(conn, user, "Business Rule Published", rule_id, "")
    conn.commit(); conn.close()
    return RedirectResponse("/rules?msg=published", status_code=303)
