"""Recovery utility: change only an existing Super Admin email address."""

import argparse
import ctypes
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_connection


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != "CHANGE-SUPERADMIN-EMAIL":
        raise SystemExit("Confirmation phrase is required")
    if sys.platform == "win32" and not ctypes.windll.shell32.IsUserAnAdmin():
        raise SystemExit("Run this recovery utility from an elevated Administrator PowerShell")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", args.email.strip()):
        raise SystemExit("Invalid email address")
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE UPPER(user_id)=UPPER(:1) AND status='Active'", (args.user_id.strip(),))
    row = cur.fetchone()
    if not row or str(row[0] or "").strip().lower() != "super admin":
        conn.close(); raise SystemExit("The account was not found or is not an active Super Admin")
    cur.execute("UPDATE users SET email=:1 WHERE UPPER(user_id)=UPPER(:2)", (args.email.strip(), args.user_id.strip()))
    conn.commit(); conn.close()
    print(f"Super Admin email updated for {args.user_id}.")


if __name__ == "__main__":
    main()
