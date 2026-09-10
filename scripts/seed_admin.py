"""
Seed a SUPER ADMIN login for RentaGO Web.

Creates a user in the users table with a VBA-compatible salted SHA-256 hash so
the web app can authenticate immediately (before/without importing the xlsm).

Usage:
    python scripts/seed_admin.py --password "Use-a-secret-password"
    python scripts/seed_admin.py --user-id admin --password "YourPass" --name "Super Admin"
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import get_connection
from app.security import hash_password


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", default="admin")
    ap.add_argument("--password", required=True, help="Provide the password securely; it is never stored in source code.")
    ap.add_argument("--name", default="Super Admin")
    ap.add_argument("--role", default="SUPER ADMIN")
    ap.add_argument("--email", default="")
    args = ap.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    ph = hash_password(args.password)
    cur.execute("SELECT COUNT(*) FROM users WHERE UPPER(user_id)=UPPER(:1)", (args.user_id,))
    exists = int(cur.fetchone()[0])
    if exists:
        cur.execute(
            "UPDATE users SET password_hash=:1, name=:2, role=:3, email=:4, status='Active' "
            "WHERE UPPER(user_id)=UPPER(:5)",
            (ph, args.name, args.role, args.email, args.user_id),
        )
        print(f"Updated {args.user_id}")
    else:
        cur.execute("SELECT NVL(MAX(user_no),0)+1 FROM users")
        nxt = int(cur.fetchone()[0])
        cur.execute(
            "INSERT INTO users (user_no, user_id, name, email, company_name, role, status, password_hash) "
            "VALUES (:1,:2,:3,:4,'RentaGO HQ',:5,'Active',:6)",
            (nxt, args.user_id, args.name, args.email, args.role, ph),
        )
        print(f"Created {args.user_id}")

    conn.commit()
    conn.close()
    print("Super admin ready. Log in with user_id:", args.user_id)


if __name__ == "__main__":
    main()
