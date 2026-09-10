"""Deactivate non-Super-Admin accounts without deleting historical data."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_connection


def main():
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT COUNT(1) FROM users WHERE LOWER(NVL(role,'')) <> 'super admin' AND NVL(status,'Active') <> 'Inactive'")
    user_count = int(cur.fetchone()[0] or 0)
    cur.execute("UPDATE users SET status='Inactive' WHERE LOWER(NVL(role,'')) <> 'super admin'")
    cur.execute("DELETE FROM user_sessions WHERE UPPER(user_id) IN (SELECT UPPER(user_id) FROM users WHERE LOWER(NVL(role,'')) <> 'super admin')")
    session_count = cur.rowcount
    cur.execute("UPDATE otp_log SET status='Expired', used_dt=SYSDATE WHERE UPPER(user_id) IN (SELECT UPPER(user_id) FROM users WHERE LOWER(NVL(role,'')) <> 'super admin') AND status='Active'")
    otp_count = cur.rowcount
    cur.execute("UPDATE tenant_memberships SET status='SUSPENDED' WHERE UPPER(user_id) IN (SELECT UPPER(user_id) FROM users WHERE LOWER(NVL(role,'')) <> 'super admin') AND status='ACTIVE'")
    membership_count = cur.rowcount
    cur.execute(
        "INSERT INTO audit_log (audit_date,audit_time,user_id,audit_user,action,record,notes) "
        "VALUES (SYSDATE,TO_CHAR(SYSDATE,'HH24:MI:SS'),'SYSTEM','System Account Reset','DEACTIVATE_NON_SUPERADMINS','Users',:1)",
        (f"users={user_count}; sessions={session_count}; otp={otp_count}; memberships={membership_count}",),
    )
    conn.commit(); conn.close()
    print(f"Deactivated users: {user_count}")
    print(f"Revoked sessions: {session_count}")
    print(f"Expired OTPs: {otp_count}")
    print(f"Suspended memberships: {membership_count}")
    print("Historical business data was preserved.")


if __name__ == "__main__":
    main()
