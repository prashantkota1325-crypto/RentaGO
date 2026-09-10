"""
RentaGO Web - one-time database bootstrap.

Connects as the DBA user (default SYSTEM) and:
  1. Creates the RENTAGO user (if absent).
  2. Grants it the needed privileges.
  3. Runs db/schema/schema.sql as RENTAGO to create all tables.

Requires: Oracle XE 21c running, and RENTAGO_ADMIN_USER / RENTAGO_ADMIN_PASSWORD
set (see .env.example; default SYSTEM / password from env).

Usage:  python scripts/setup_db.py
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import oracledb
from app.config import settings

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "db" / "schema" / "schema.sql"
APP_USER = settings.DB_USER.upper()
APP_PWD = settings.DB_PASSWORD


def main():
    admin_user = os.environ.get("RENTAGO_ADMIN_USER", "SYSTEM")
    admin_pwd = os.environ.get("RENTAGO_ADMIN_PASSWORD", "")
    if not admin_pwd:
        print("No RENTAGO_ADMIN_PASSWORD set; using 'oracle'. Set it in .env to avoid surprises.")
        admin_pwd = "oracle"

    oracledb.init_oracle_client(lib_dir=os.environ.get("RENTAGO_ORACLE_CLIENT"))
    print(f"Connecting as {admin_user} to {settings.admin_dsn} ...")
    conn = oracledb.connect(user=admin_user, password=admin_pwd, dsn=settings.admin_dsn)
    cur = conn.cursor()

    # 1. Create app user if it doesn't exist
    cur.execute("SELECT COUNT(*) FROM all_users WHERE UPPER(username)=:1", (APP_USER,))
    exists = cur.fetchone()[0]
    if not exists:
        quoted = f'"{APP_USER}"'
        cur.execute(f'CREATE USER {quoted} IDENTIFIED BY "{APP_PWD}" DEFAULT TABLESPACE USERS QUOTA UNLIMITED ON USERS')
        cur.execute(f'GRANT CONNECT, RESOURCE TO {quoted}')
        print(f"Created user {APP_USER}")
    else:
        cur.execute(f'ALTER USER "{APP_USER}" IDENTIFIED BY "{APP_PWD}"')
        print(f"User {APP_USER} already exists; password refreshed")

    # 2. Run schema
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    # Switch to the app user context for table creation.
    print(f"Running {SCHEMA_FILE.name} as {APP_USER} ...")
    app_conn = oracledb.connect(user=APP_USER, password=APP_PWD, dsn=settings.dsn)
    script_cur = app_conn.cursor()
    # Execute statements split on ';' (handles simple DDL/DML; no PL/SQL blocks expected yet)
    stmts = [s.strip() for s in sql.replace("\n", " ").split(";") if s.strip()]
    for stmt in stmts:
        try:
            script_cur.execute(stmt)
        except oracledb.DatabaseError as e:
            print(f"  [warn] statement skipped: {e}")
    app_conn.commit()
    app_conn.close()

    conn.commit()
    conn.close()
    print("Done. Schema is ready.")


if __name__ == "__main__":
    main()
