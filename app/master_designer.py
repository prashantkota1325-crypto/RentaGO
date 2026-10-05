"""Metadata-driven Master Designer support.

The existing ``MASTERS`` dictionary remains the safe bootstrap/default source.
Published metadata is an overlay consumed by the existing import/export engine;
it does not create SQL identifiers or physical business-table columns.
"""

import json
import re
import uuid
from datetime import datetime

from .master_import import ALIASES

FIELD_TYPES = {
    "TEXT", "LONG_TEXT", "NUMBER", "DECIMAL", "DATE", "DATETIME", "EMAIL",
    "MOBILE", "BOOLEAN", "DROPDOWN", "MULTI_SELECT", "COMPANY_LOOKUP",
    "VENDOR_LOOKUP", "VEHICLE_LOOKUP", "DRIVER_LOOKUP", "EMPLOYEE_LOOKUP",
    "CONTRACT_LOOKUP", "USER_LOOKUP", "FILE",
}
TECHNICAL_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
PROTECTED_FIELDS = {
    "tenant_id", "created_at", "created_by", "updated_at", "updated_by",
    "password", "password_hash", "password_vault", "otp_secret", "api_key",
    "secret_key", "private_key",
}


def normalize_header(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def validate_technical_name(value):
    value = str(value or "").strip()
    if not TECHNICAL_NAME.fullmatch(value):
        raise ValueError("Technical name must match ^[a-z][a-z0-9_]*$.")
    if value in PROTECTED_FIELDS or value.endswith("_id") and value in {"user_id", "tenant_id"}:
        raise ValueError("This technical name is system protected.")
    return value


def field_type(value):
    value = str(value or "TEXT").strip().upper()
    if value not in FIELD_TYPES:
        raise ValueError("Unsupported field type.")
    return value


def _bool(value, default="N"):
    if value is None:
        return default
    return "Y" if str(value).strip().upper() in {"Y", "YES", "TRUE", "1", "ON"} else "N"


def master_keys():
    return (
        "companies", "corporate-admin-contacts", "contacts", "employees",
        "rentago-employees", "vendors", "vehicles", "drivers", "individuals",
        "contracts", "ratecards", "leads", "settings",
    )


def _field_seed(cfg, key):
    labels = {name: label for name, label in cfg.get("list", [])}
    fields = []
    seen = set()
    pk = cfg.get("pk")
    if pk:
        fields.append({"technical_name": pk, "display_label": labels.get(pk, pk.replace("_", " ").title()),
                       "excel_header": labels.get(pk, pk.replace("_", " ").title()), "field_type": "TEXT",
                       "required": "N", "import_enabled": "N", "export_enabled": "Y",
                       "system_protected": "Y", "generated_field": "Y", "display_order": 1})
        seen.add(pk)
    order = 2
    if cfg.get("table") in {"companies", "company_entities", "employees", "vendors", "vehicles", "drivers", "individuals", "contacts", "contracts", "ratecards", "leads", "settings"}:
        fields.append({"technical_name": "tenant_id", "display_label": "Tenant ID", "excel_header": "Tenant ID", "field_type": "TEXT",
                       "required": "N", "import_enabled": "N", "export_enabled": "N", "system_protected": "Y",
                       "generated_field": "Y", "display_order": order})
        seen.add("tenant_id")
        order += 1
    for item in cfg.get("fields", []):
        name = item["name"]
        if name in seen:
            continue
        raw_type = item.get("type", "text").upper()
        mapped_type = {"SELECT": "DROPDOWN", "TEL": "MOBILE"}.get(raw_type, raw_type)
        if mapped_type not in FIELD_TYPES:
            mapped_type = "TEXT"
        protected = name in PROTECTED_FIELDS
        generated = name == pk or name in {"created_at", "updated_at"}
        fields.append({"technical_name": name, "display_label": item.get("label") or labels.get(name, name),
                       "excel_header": labels.get(name, item.get("label") or name), "field_type": mapped_type,
                       "required": _bool("Y" if item.get("required") else "N"),
                       "import_enabled": "N" if protected or generated or key == "ratecards" else "Y",
                       "export_enabled": "N" if protected else "Y", "system_protected": "Y" if protected else "N",
                       "generated_field": "Y" if generated else "N", "display_order": order,
                       "validation_rule": "EMAIL" if mapped_type == "EMAIL" else None})
        seen.add(name)
        order += 1
    return fields


def seed_metadata(conn, masters):
    """Idempotently seed definitions/fields/options from existing configuration."""
    cur = conn.cursor()
    for key in master_keys():
        cfg = masters[key]
        master_id = "MD-" + uuid.uuid5(uuid.NAMESPACE_URL, "rentago:master:" + key).hex[:28].upper()
        cur.execute("SELECT master_id FROM master_definitions WHERE master_key=:1", (key,))
        row = cur.fetchone()
        if row:
            master_id = row[0]
            cur.execute("UPDATE master_definitions SET display_name=:1,updated_at=SYSTIMESTAMP,updated_by='SYSTEM' WHERE master_id=:2", (cfg["title"], master_id))
        else:
            cur.execute(
                "INSERT INTO master_definitions (master_id,master_key,display_name,database_table,route_key,description,active,import_enabled,export_enabled,version,tenant_scoped,created_at,created_by,updated_at,updated_by) "
                "VALUES (:1,:2,:3,:4,:5,:6,'Y',:7,'Y',1,:8,SYSTIMESTAMP,'SYSTEM',SYSTIMESTAMP,'SYSTEM')",
                (master_id, key, cfg["title"], cfg["table"], key, "RentaGO Master metadata",
                 "N" if cfg.get("import_blocked") else "Y", "Y" if cfg["table"] in {"companies", "employees", "vendors", "vehicles", "drivers", "individuals", "contacts", "contracts", "ratecards", "leads", "settings", "company_entities"} else "N"),
            )
        for definition in _field_seed(cfg, key):
            cur.execute("SELECT field_id FROM master_field_definitions WHERE master_id=:1 AND technical_name=:2",
                        (master_id, definition["technical_name"]))
            existing_field = cur.fetchone()
            field_id = existing_field[0] if existing_field else "MF-" + uuid.uuid4().hex[:28].upper()
            if existing_field and definition["technical_name"] == cfg.get("pk"):
                cur.execute("UPDATE master_field_definitions SET export_enabled='Y' WHERE field_id=:1", (field_id,))
            if not existing_field:
                cur.execute(
                    "INSERT INTO master_field_definitions (field_id,master_id,technical_name,display_label,excel_header,field_type,required,active,display_enabled,import_enabled,export_enabled,searchable,filterable,sortable,display_order,system_protected,generated_field,custom_field,validation_rule,created_at,created_by,updated_at,updated_by) "
                    "VALUES (:1,:2,:3,:4,:5,:6,:7,'Y','Y',:8,:9,'N','N','N',:10,:11,:12,'N',:13,SYSTIMESTAMP,'SYSTEM',SYSTIMESTAMP,'SYSTEM')",
                    (field_id, master_id, definition["technical_name"], definition["display_label"], definition["excel_header"], definition["field_type"], definition["required"], definition["import_enabled"], definition["export_enabled"], definition["display_order"], definition["system_protected"], definition["generated_field"], definition.get("validation_rule")),
                )
            aliases = {definition["technical_name"], definition["display_label"], definition["excel_header"]}
            aliases.update(alias for alias, target in ALIASES.get(cfg["table"], {}).items() if target == definition["technical_name"])
            for alias in aliases:
                cur.execute("SELECT COUNT(*) FROM master_field_aliases WHERE field_id=:1 AND normalized_alias=:2", (field_id, normalize_header(alias)))
                if cur.fetchone()[0] == 0:
                    cur.execute("INSERT INTO master_field_aliases (alias_id,field_id,alias_value,normalized_alias) VALUES (:1,:2,:3,:4)", (uuid.uuid4().hex, field_id, alias, normalize_header(alias)))
            source_field = next((item for item in cfg.get("fields", []) if item["name"] == definition["technical_name"]), None)
            for number, option in enumerate((source_field or {}).get("options") or (), 1):
                cur.execute("SELECT COUNT(*) FROM master_field_options WHERE field_id=:1 AND option_value=:2", (field_id, str(option)))
                if cur.fetchone()[0] == 0:
                    cur.execute("INSERT INTO master_field_options (option_id,field_id,option_value,display_label,display_order) VALUES (:1,:2,:3,:4,:5)", (uuid.uuid4().hex, field_id, str(option), str(option), number))
    conn.commit()


def load_published_config(conn, key, fallback):
    """Overlay a published JSON snapshot when one exists; otherwise fallback."""
    cur = conn.cursor()
    cur.execute("SELECT config_json FROM master_configuration_versions v JOIN master_definitions d ON d.master_id=v.master_id WHERE d.master_key=:1 AND v.status='PUBLISHED' ORDER BY v.version_no DESC FETCH FIRST 1 ROWS ONLY", (key,))
    row = cur.fetchone()
    if not row or not row[0]:
        return fallback
    raw = row[0].read() if hasattr(row[0], "read") else row[0]
    try:
        snapshot = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback
    result = dict(fallback)
    result["_metadata_master_id"] = None
    cur.execute("SELECT master_id FROM master_definitions WHERE master_key=:1", (key,))
    master_row = cur.fetchone()
    if master_row:
        result["_metadata_master_id"] = master_row[0]
    if "fields" in snapshot:
        result["fields"] = [field for field in snapshot["fields"]
                             if field.get("import_enabled") and not field.get("system_protected")
                             and not field.get("generated_field")]
        if not any(field.get("name") == fallback.get("pk") for field in result["fields"]):
            result["fields"].insert(0, {"name": fallback.get("pk"), "label": fallback.get("pk", "ID"),
                                         "type": "text", "required": True, "import_enabled": True,
                                         "export_enabled": False, "generated_field": True,
                                         "system_protected": True, "custom_field": False,
                                         "aliases": [fallback.get("pk", "ID")]})
    if "list" in snapshot:
        result["list"] = [item for item, field in zip(snapshot["list"], snapshot.get("fields", []))
                           if field.get("export_enabled") and field.get("display_enabled", True)]
        if fallback.get("pk") and not any(item[0] == fallback["pk"] for item in result["list"]):
            result["list"].insert(0, (fallback["pk"], fallback["pk"].replace("_", " ").title()))
    result.update({name: snapshot[name] for name in ("search", "filters", "date_filters") if name in snapshot})
    return result


def save_custom_values(conn, master_id, tenant_id, record_id, fields, row, user_id):
    if not master_id:
        return
    cur = conn.cursor()
    for field in fields:
        if not field.get("custom_field") or field.get("name") not in row:
            continue
        cur.execute("SELECT custom_value_id FROM master_custom_values WHERE master_id=:1 AND tenant_id=:2 AND record_id=:3 AND field_id=:4",
                    (master_id, tenant_id, str(record_id), field.get("field_id")))
        value = str(row.get(field["name"]) or "")[:4000]
        existing = cur.fetchone()
        if existing:
            cur.execute("UPDATE master_custom_values SET value_text=:1,updated_at=SYSTIMESTAMP,updated_by=:2 WHERE custom_value_id=:3", (value, user_id, existing[0]))
        else:
            cur.execute("INSERT INTO master_custom_values (custom_value_id,master_id,tenant_id,record_id,field_id,value_text,updated_by) VALUES (:1,:2,:3,:4,:5,:6,:7)", (uuid.uuid4().hex, master_id, tenant_id, str(record_id), field.get("field_id"), value, user_id))


def snapshot_config(conn, master_id):
    cur = conn.cursor()
    cur.execute("SELECT field_id,technical_name,display_label,excel_header,field_type,required,import_enabled,export_enabled,display_enabled,display_order,system_protected,generated_field,custom_field,validation_rule FROM master_field_definitions WHERE master_id=:1 AND active='Y' ORDER BY display_order,technical_name", (master_id,))
    fields = []
    listing = []
    for row in cur.fetchall():
        field_id, name, label, excel, ftype, required, importing, exporting, display, order, protected, generated, custom, rule = row
        cur.execute("SELECT alias_value FROM master_field_aliases WHERE field_id=:1 AND active='Y'", (field_id,))
        aliases = [item[0] for item in cur.fetchall()]
        cur.execute("SELECT option_value FROM master_field_options WHERE field_id=:1 AND active='Y' ORDER BY display_order", (field_id,))
        options = [item[0] for item in cur.fetchall()]
        fields.append({"field_id": field_id, "name": name, "label": label, "type": ftype.lower(), "required": required == "Y", "import_enabled": importing == "Y", "export_enabled": exporting == "Y", "display_enabled": display == "Y", "system_protected": protected == "Y", "generated_field": generated == "Y", "custom_field": custom == "Y", "excel_header": excel, "validation_rule": rule, "aliases": aliases, "options": options})
        if display == "Y":
            listing.append((name, label))
    return {"fields": fields, "list": listing}
