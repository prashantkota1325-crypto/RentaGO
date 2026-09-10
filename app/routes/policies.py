"""Internal RentaGO policy definition and version administration."""

from datetime import datetime
import uuid
import csv
import io

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, Response

from ..auth import current_user, module_level
from ..db import get_connection
from ..templating import templates
from ..audit import audit
from ..config_validation import json_object

router = APIRouter(prefix="/policies")
CATEGORIES = ("Booking", "Cancellation", "Refund", "Vendor", "Driver", "Fleet",
              "Finance", "Safety", "Compliance", "Customer Service", "IT")


def _allowed(user):
    return bool(user) and module_level(user, "Policies") is not None


def _editable(user):
    return bool(user) and module_level(user, "Policies") == "F"


@router.get("")
def policy_list(request: Request, status: str = ""):
    user = current_user(request)
    if not _allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    sql = "SELECT policy_id, policy_name, category, department, current_version, status, created_by, approved_by FROM policy_definitions"
    params = []
    if status:
        sql += " WHERE status=:1"; params.append(status)
    sql += " ORDER BY policy_name"
    cur.execute(sql, params or None)
    rows = [dict(zip(("policy_id", "policy_name", "category", "department", "version", "status", "created_by", "approved_by"), r)) for r in cur.fetchall()]
    conn.close()
    return templates.TemplateResponse("policies/list.html", {"request": request, "user": user, "rows": rows, "can_edit": _editable(user), "status_filter": status, "categories": CATEGORIES})


@router.get("/export")
def policy_export(request: Request):
    user = current_user(request)
    if not _allowed(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "SELECT p.policy_id,p.policy_name,p.category,p.department,p.current_version,p.status, "
        "v.policy_version_id,v.condition_definition,v.action_definition,v.status,v.change_reason "
        "FROM policy_definitions p LEFT JOIN policy_versions v ON v.policy_id=p.policy_id AND v.version=p.current_version "
        "ORDER BY p.policy_name")
    buf = io.StringIO(); writer = csv.writer(buf)
    writer.writerow(["Policy ID", "Policy Name", "Category", "Department", "Version", "Policy Status", "Version ID", "Conditions JSON", "Actions JSON", "Version Status", "Change Reason"])
    writer.writerows(cur.fetchall())
    audit(conn, user, "Policy Configuration Exported", "Policies", "")
    conn.commit(); conn.close()
    return Response(content=buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="rentago-policies.csv"'})


@router.post("/import")
def policy_import(request: Request, file: UploadFile = File(...)):
    user = current_user(request)
    if not _editable(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    try:
        reader = csv.DictReader(io.StringIO(file.file.read().decode("utf-8-sig")))
        required = {"Policy Name", "Category", "Conditions JSON", "Actions JSON"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("missing CSV columns")
        count = 0
        for row in list(reader)[:5000]:
            category = (row.get("Category") or "").strip()
            if category not in CATEGORIES:
                raise ValueError("invalid category")
            conditions = json_object(row.get("Conditions JSON"), "Conditions")
            actions = json_object(row.get("Actions JSON"), "Actions")
            policy_id = (row.get("Policy ID") or "").strip()
            cur.execute("SELECT policy_id FROM policy_definitions WHERE policy_id=:1", (policy_id,))
            exists = cur.fetchone()
            if not exists:
                policy_id = policy_id[:40] if policy_id else "POL-" + uuid.uuid4().hex[:20]
                cur.execute("INSERT INTO policy_definitions (policy_id,policy_name,category,department,current_version,status,created_by) VALUES (:1,:2,:3,:4,1,'Draft',:5)",
                            (policy_id, (row.get("Policy Name") or "Imported")[:200], category, (row.get("Department") or "").strip() or None, user["user_id"]))
                version = 1
            else:
                cur.execute("SELECT NVL(MAX(version),0)+1 FROM policy_versions WHERE policy_id=:1", (policy_id,)); version = int(cur.fetchone()[0])
                cur.execute("UPDATE policy_definitions SET current_version=:1,status='Draft' WHERE policy_id=:2", (version, policy_id))
            cur.execute("INSERT INTO policy_versions (policy_version_id,policy_id,version,condition_definition,action_definition,status,change_reason,created_by) VALUES (:1,:2,:3,:4,:5,'Draft',:6,:7)",
                        ("POLV-" + uuid.uuid4().hex[:20], policy_id, version, conditions, actions, "Imported CSV", user["user_id"]))
            count += 1
        audit(conn, user, "Policy Configuration Imported", "Policies", f"rows={count}")
        conn.commit()
    except Exception:
        conn.rollback(); conn.close()
        return RedirectResponse("/policies?msg=import-error", status_code=303)
    conn.close()
    return RedirectResponse("/policies?msg=imported", status_code=303)


@router.get("/new")
def policy_new(request: Request, source_id: str = ""):
    user = current_user(request)
    if not _editable(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    record = {}
    if source_id:
        conn = get_connection(); cur = conn.cursor()
        cur.execute(
            "SELECT p.policy_name,p.category,p.department,v.condition_definition,v.action_definition "
            "FROM policy_definitions p JOIN policy_versions v ON v.policy_id=p.policy_id "
            "WHERE p.policy_id=:1 AND v.version=p.current_version", (source_id,))
        row = cur.fetchone(); conn.close()
        if row:
            record = dict(zip(("policy_name", "category", "department", "conditions", "actions"), row))
    return templates.TemplateResponse("policies/form.html", {"request": request, "user": user, "categories": CATEGORIES, "record": record, "source_id": source_id})


@router.post("/save")
def policy_save(request: Request, policy_name: str = Form(...), category: str = Form(...),
                department: str = Form(""), conditions: str = Form(""),
                actions: str = Form(""), change_reason: str = Form(""),
                source_policy_id: str = Form("")):
    user = current_user(request)
    if not _editable(user) or category not in CATEGORIES:
        return RedirectResponse("/policies?msg=not-allowed", status_code=303)
    try:
        conditions = json_object(conditions, "Conditions")
        actions = json_object(actions, "Actions")
    except ValueError:
        return RedirectResponse("/policies?msg=invalid-json", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    if source_policy_id:
        cur.execute("SELECT policy_id FROM policy_definitions WHERE policy_id=:1", (source_policy_id,))
        if not cur.fetchone():
            conn.close(); return RedirectResponse("/policies?msg=not-found", status_code=303)
        policy_id = source_policy_id
        cur.execute("SELECT NVL(MAX(version),0)+1 FROM policy_versions WHERE policy_id=:1", (policy_id,))
        version = int(cur.fetchone()[0])
        cur.execute("UPDATE policy_definitions SET current_version=:1, status='Draft' WHERE policy_id=:2", (version, policy_id))
    else:
        policy_id = "POL-" + uuid.uuid4().hex[:20]
        version = 1
        cur.execute(
            "INSERT INTO policy_definitions (policy_id, policy_name, category, department, current_version, status, created_by) "
            "VALUES (:1,:2,:3,:4,1,'Draft',:5)",
            (policy_id, policy_name.strip(), category, department.strip() or None, user["user_id"]),
        )
    version_id = "POLV-" + uuid.uuid4().hex[:20]
    cur.execute(
        "INSERT INTO policy_versions (policy_version_id, policy_id, version, condition_definition, action_definition, status, change_reason, created_by) "
        "VALUES (:1,:2,:3,:4,:5,'Draft',:6,:7)",
        (version_id, policy_id, version, conditions.strip() or None, actions.strip() or None,
         change_reason.strip()[:1000] or None, user["user_id"]),
    )
    audit(conn, user, "Policy Draft Created", policy_id, policy_name)
    conn.commit(); conn.close()
    return RedirectResponse("/policies?msg=created", status_code=303)


@router.post("/{policy_id}/publish")
def policy_publish(request: Request, policy_id: str):
    user = current_user(request)
    if not _editable(user):
        return RedirectResponse("/home?msg=access-denied", status_code=303)
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT v.condition_definition,v.action_definition FROM policy_versions v JOIN policy_definitions p ON p.policy_id=v.policy_id WHERE p.policy_id=:1 AND v.version=p.current_version", (policy_id,))
    row = cur.fetchone()
    try:
        if not row:
            raise ValueError("policy version not found")
        json_object(row[0], "Conditions")
        json_object(row[1], "Actions")
    except ValueError:
        conn.close(); return RedirectResponse("/policies?msg=invalid-json", status_code=303)
    cur.execute("UPDATE policy_definitions SET status='Published', approved_by=:1 WHERE policy_id=:2", (user["user_id"], policy_id))
    cur.execute("UPDATE policy_versions SET status='Archived' WHERE policy_id=:1 AND status='Published'", (policy_id,))
    cur.execute("UPDATE policy_versions SET status='Published', approved_by=:1, approved_dt=SYSDATE WHERE policy_id=:2 AND version=(SELECT current_version FROM policy_definitions WHERE policy_id=:2)", (user["user_id"], policy_id))
    audit(conn, user, "Policy Published", policy_id, "")
    conn.commit(); conn.close()
    return RedirectResponse("/policies?msg=published", status_code=303)
