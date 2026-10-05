"""LAB-only additive Master Designer metadata migration and bootstrap."""

import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.db import get_connection
from app.master_designer import seed_metadata, snapshot_config
from app.routes.masters import MASTERS


TABLES = {
    "MASTER_DEFINITIONS": """CREATE TABLE master_definitions (
        master_id VARCHAR2(40) PRIMARY KEY, master_key VARCHAR2(80) NOT NULL UNIQUE,
        display_name VARCHAR2(160) NOT NULL, database_table VARCHAR2(80) NOT NULL,
        route_key VARCHAR2(80) NOT NULL, description VARCHAR2(1000), active CHAR(1) DEFAULT 'Y' NOT NULL,
        import_enabled CHAR(1) DEFAULT 'Y' NOT NULL, export_enabled CHAR(1) DEFAULT 'Y' NOT NULL,
        version NUMBER(10) DEFAULT 1 NOT NULL, tenant_scoped CHAR(1) DEFAULT 'N' NOT NULL,
        created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL, created_by VARCHAR2(160),
        updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL, updated_by VARCHAR2(160)
    )""",
    "MASTER_FIELD_DEFINITIONS": """CREATE TABLE master_field_definitions (
        field_id VARCHAR2(40) PRIMARY KEY, master_id VARCHAR2(40) NOT NULL,
        technical_name VARCHAR2(128) NOT NULL, display_label VARCHAR2(200) NOT NULL,
        excel_header VARCHAR2(200) NOT NULL, field_type VARCHAR2(40) NOT NULL,
        required CHAR(1) DEFAULT 'N' NOT NULL, default_value VARCHAR2(2000), placeholder VARCHAR2(500),
        help_text VARCHAR2(1000), active CHAR(1) DEFAULT 'Y' NOT NULL, display_enabled CHAR(1) DEFAULT 'Y' NOT NULL,
        import_enabled CHAR(1) DEFAULT 'Y' NOT NULL, export_enabled CHAR(1) DEFAULT 'Y' NOT NULL,
        searchable CHAR(1) DEFAULT 'N' NOT NULL, filterable CHAR(1) DEFAULT 'N' NOT NULL,
        sortable CHAR(1) DEFAULT 'N' NOT NULL, display_order NUMBER(10) NOT NULL,
        system_protected CHAR(1) DEFAULT 'N' NOT NULL, generated_field CHAR(1) DEFAULT 'N' NOT NULL,
        custom_field CHAR(1) DEFAULT 'N' NOT NULL, validation_rule VARCHAR2(80),
        min_length NUMBER(10), max_length NUMBER(10), min_value NUMBER, max_value NUMBER,
        regex_pattern VARCHAR2(1000), created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
        created_by VARCHAR2(160), updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL, updated_by VARCHAR2(160),
        CONSTRAINT uq_master_field_name UNIQUE (master_id,technical_name),
        CONSTRAINT fk_master_field_master FOREIGN KEY (master_id) REFERENCES master_definitions(master_id)
    )""",
    "MASTER_FIELD_OPTIONS": """CREATE TABLE master_field_options (
        option_id VARCHAR2(40) PRIMARY KEY, field_id VARCHAR2(40) NOT NULL,
        option_value VARCHAR2(200) NOT NULL, display_label VARCHAR2(200) NOT NULL,
        display_order NUMBER(10) DEFAULT 1 NOT NULL, active CHAR(1) DEFAULT 'Y' NOT NULL,
        CONSTRAINT uq_master_field_option UNIQUE (field_id,option_value),
        CONSTRAINT fk_master_option_field FOREIGN KEY (field_id) REFERENCES master_field_definitions(field_id)
    )""",
    "MASTER_FIELD_ALIASES": """CREATE TABLE master_field_aliases (
        alias_id VARCHAR2(40) PRIMARY KEY, field_id VARCHAR2(40) NOT NULL,
        alias_value VARCHAR2(200) NOT NULL, normalized_alias VARCHAR2(200) NOT NULL,
        active CHAR(1) DEFAULT 'Y' NOT NULL,
        CONSTRAINT uq_master_field_alias UNIQUE (field_id,normalized_alias),
        CONSTRAINT fk_master_alias_field FOREIGN KEY (field_id) REFERENCES master_field_definitions(field_id)
    )""",
    "MASTER_CUSTOM_VALUES": """CREATE TABLE master_custom_values (
        custom_value_id VARCHAR2(40) PRIMARY KEY, master_id VARCHAR2(40) NOT NULL,
        tenant_id VARCHAR2(40) NOT NULL, record_id VARCHAR2(100) NOT NULL,
        field_id VARCHAR2(40) NOT NULL, value_text VARCHAR2(4000),
        updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL, updated_by VARCHAR2(160),
        CONSTRAINT uq_master_custom_value UNIQUE (master_id,tenant_id,record_id,field_id),
        CONSTRAINT fk_custom_value_master FOREIGN KEY (master_id) REFERENCES master_definitions(master_id),
        CONSTRAINT fk_custom_value_field FOREIGN KEY (field_id) REFERENCES master_field_definitions(field_id)
    )""",
    "MASTER_CONFIGURATION_VERSIONS": """CREATE TABLE master_configuration_versions (
        config_version_id VARCHAR2(40) PRIMARY KEY, master_id VARCHAR2(40) NOT NULL,
        version_no NUMBER(10) NOT NULL, status VARCHAR2(20) NOT NULL,
        config_json CLOB NOT NULL, created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
        created_by VARCHAR2(160), published_at TIMESTAMP, published_by VARCHAR2(160),
        CONSTRAINT uq_master_config_version UNIQUE (master_id,version_no),
        CONSTRAINT fk_master_config_master FOREIGN KEY (master_id) REFERENCES master_definitions(master_id)
    )""",
    "MASTER_CONFIGURATION_AUDIT": """CREATE TABLE master_configuration_audit (
        config_audit_id VARCHAR2(40) PRIMARY KEY, tenant_id VARCHAR2(40), user_id VARCHAR2(160),
        master_id VARCHAR2(40) NOT NULL, field_id VARCHAR2(40), config_version_id VARCHAR2(40),
        action VARCHAR2(60) NOT NULL, old_value VARCHAR2(2000), new_value VARCHAR2(2000),
        audit_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
        CONSTRAINT fk_master_audit_master FOREIGN KEY (master_id) REFERENCES master_definitions(master_id)
    )""",
}


def main():
    if settings.ENVIRONMENT == "production" or settings.DB_HOST not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("Refusing Master Designer migration outside local LAB.")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM user_tables")
    existing = {row[0] for row in cur.fetchall()}
    for name, ddl in TABLES.items():
        if name not in existing:
            cur.execute(ddl)
            print("[added]", name)
    conn.commit()
    seed_metadata(conn, MASTERS)
    cur = conn.cursor()
    from app.master_designer import master_keys
    for key in master_keys():
        cur.execute("SELECT master_id FROM master_definitions WHERE master_key=:1", (key,))
        master_id = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM master_configuration_versions WHERE master_id=:1", (master_id,))
        if cur.fetchone()[0]:
            continue
        snapshot = snapshot_config(conn, master_id)
        cur.execute("INSERT INTO master_configuration_versions (config_version_id,master_id,version_no,status,config_json,created_by,published_at,published_by) VALUES (:1,:2,1,'PUBLISHED',:3,'SYSTEM',SYSTIMESTAMP,'SYSTEM')",
                    ("MCV-" + uuid.uuid4().hex[:28].upper(), master_id, json.dumps(snapshot)))
    conn.commit()
    conn.close()
    print("LAB Master Designer migration complete.")


if __name__ == "__main__":
    main()
