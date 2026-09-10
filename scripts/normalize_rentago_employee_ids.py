import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.db import get_connection

conn = get_connection()
cur = conn.cursor()
cur.execute(
    "SELECT emp_id FROM employees "
    "WHERE UPPER(TRIM(company_name))=UPPER(TRIM(:1)) ORDER BY emp_id",
    ("RentaGO Technologies Pvt Ltd",),
)
updates = []
for (old_id,) in cur.fetchall():
    if str(old_id or "").upper().startswith("RG-E-"):
        continue
    cur.execute("SELECT rentago_emp_seq.NEXTVAL FROM dual")
    new_id = "RG-E-" + str(cur.fetchone()[0])
    cur.execute("UPDATE employees SET emp_id=:1 WHERE emp_id=:2", (new_id, old_id))
    updates.append((old_id, new_id))
conn.commit()
print("Updated:", updates)
conn.close()
