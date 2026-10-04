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
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import get_connection
from app.master_designer import seed_metadata
from app.routes.masters import MASTERS
from migrate_master_designer import TABLES


def _existing_columns(cur, table):
    cur.execute("SELECT column_name FROM user_tab_columns WHERE table_name=:1", (table,))
    return {row[0] for row in cur.fetchall()}


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
        if not _existing_columns(cur, table):
            raise RuntimeError(f"Existing {table} has no readable columns; manual review required.")
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
