"""Reviewed Production migration design for Master Designer metadata.

This file is intentionally inert unless both explicit runtime gates are
provided. It creates only missing metadata tables and seeds metadata by stable
Master/field technical keys. It never imports business data.

Required future execution gates:
    python scripts/migrate_master_designer_production.py --apply
    RENTAGO_APPROVE_MASTER_DESIGNER_MIGRATION=YES
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import get_connection
from app.master_designer import seed_metadata
from app.routes.masters import MASTERS
from migrate_master_designer import TABLES


def _expected_columns(ddl):
    columns = {}
    for line in ddl.splitlines():
        match = re.match(r"\s*([A-Za-z][A-Za-z0-9_]*)\s+([A-Za-z]+(?:\(\d+(?:,\d+)?\))?)", line.strip().rstrip(","))
        if match and match.group(1).upper() not in {"CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN"}:
            columns[match.group(1).upper()] = match.group(2).upper()
    return columns


def _expected_constraints(ddl):
    return set(re.findall(r"CONSTRAINT\s+([A-Za-z][A-Za-z0-9_]*)", ddl, re.IGNORECASE))


def _verify_existing_object(cur, table, ddl):
    expected = _expected_columns(ddl)
    cur.execute("SELECT column_name,data_type FROM user_tab_columns WHERE table_name=:1", (table,))
    actual = {row[0]: row[1] for row in cur.fetchall()}
    missing = sorted(set(expected) - set(actual))
    mismatched = sorted(name for name, data_type in expected.items()
                        if name in actual and actual[name].upper() != data_type.split("(", 1)[0])
    if missing or mismatched:
        raise RuntimeError(f"Existing {table} metadata mismatch: missing={missing}; type_mismatch={mismatched}")
    named_constraints = _expected_constraints(ddl)
    if named_constraints:
        cur.execute("SELECT constraint_name FROM user_constraints WHERE table_name=:1", (table,))
        existing_constraints = {row[0] for row in cur.fetchall()}
        missing_constraints = sorted(named_constraints - existing_constraints)
        if missing_constraints:
            raise RuntimeError(f"Existing {table} constraints missing: {missing_constraints}")


def apply_migration():
    if os.environ.get("RENTAGO_APPROVE_MASTER_DESIGNER_MIGRATION") != "YES":
        raise SystemExit("Migration approval gate missing.")
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT table_name FROM user_tables")
    existing_tables = {row[0] for row in cur.fetchall()}
    for table, ddl in TABLES.items():
        if table not in existing_tables:
            cur.execute(ddl)
            continue
        # Never patch a partially matching Production object implicitly.
        _verify_existing_object(cur, table, ddl)
    conn.commit()
    seed_metadata(conn, MASTERS)
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Apply approved Master Designer metadata DDL only.")
    parser.add_argument("--apply", action="store_true", help="Required explicit execution switch.")
    args = parser.parse_args()
    if not args.apply:
        raise SystemExit("Review-only by default. Re-run with --apply after human approval.")
    apply_migration()
    print("Master Designer Production migration completed.")


if __name__ == "__main__":
    main()
