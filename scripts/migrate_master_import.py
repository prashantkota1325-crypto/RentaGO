"""LAB-only additive schema for Master Import Phase 2.

This script intentionally does not backfill or seed business data and refuses
to run when the application environment is production.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.db import get_connection


def main():
    if settings.ENVIRONMENT == "production" or settings.DB_HOST not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit("Refusing Master Import migration outside the local LAB database.")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT table_name, column_name FROM user_tab_columns")
    columns = {(table, column) for table, column in cur.fetchall()}
    for table in ("COMPANY_ENTITIES", "EMPLOYEES", "INDIVIDUALS", "CONTACTS", "CONTRACTS", "RATECARDS", "LEADS", "SETTINGS"):
        if (table, "TENANT_ID") not in columns:
            cur.execute(f"ALTER TABLE {table} ADD (TENANT_ID VARCHAR2(40))")
            print(f"[added] {table}.TENANT_ID")
    cur.execute("SELECT table_name FROM user_tables")
    tables = {row[0] for row in cur.fetchall()}
    if "MASTER_IMPORT_HISTORY" not in tables:
        cur.execute("""CREATE TABLE master_import_history (
            import_id VARCHAR2(40) PRIMARY KEY,
            preview_id VARCHAR2(80) NOT NULL UNIQUE,
            tenant_id VARCHAR2(40) NOT NULL,
            user_id VARCHAR2(160) NOT NULL,
            master_name VARCHAR2(80) NOT NULL,
            source_filename VARCHAR2(255) NOT NULL,
            source_file_hash VARCHAR2(64) NOT NULL,
            file_type VARCHAR2(10) NOT NULL,
            started_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            completed_at TIMESTAMP,
            status VARCHAR2(20) NOT NULL,
            total_rows NUMBER(12) DEFAULT 0 NOT NULL,
            valid_rows NUMBER(12) DEFAULT 0 NOT NULL,
            inserted_rows NUMBER(12) DEFAULT 0 NOT NULL,
            updated_rows NUMBER(12) DEFAULT 0 NOT NULL,
            rejected_rows NUMBER(12) DEFAULT 0 NOT NULL,
            error_count NUMBER(12) DEFAULT 0 NOT NULL,
            confirmed_at TIMESTAMP
        )""")
        print("[added] MASTER_IMPORT_HISTORY")
    if "MASTER_IMPORT_ERRORS" not in tables:
        cur.execute("""CREATE TABLE master_import_errors (
            error_id VARCHAR2(64) PRIMARY KEY,
            import_id VARCHAR2(40) NOT NULL,
            row_number NUMBER(12),
            source_field VARCHAR2(200),
            source_value VARCHAR2(500),
            canonical_field VARCHAR2(200),
            error_code VARCHAR2(60) NOT NULL,
            message VARCHAR2(1000) NOT NULL,
            created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
            CONSTRAINT fk_master_import_error FOREIGN KEY (import_id)
                REFERENCES master_import_history(import_id)
        )""")
        print("[added] MASTER_IMPORT_ERRORS")
    conn.commit()
    conn.close()
    print("LAB Master Import migration complete.")


if __name__ == "__main__":
    main()
