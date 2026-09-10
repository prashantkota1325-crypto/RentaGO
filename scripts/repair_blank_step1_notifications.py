"""Repair legacy blank Step 1 notification outbox records."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_connection
from app.notify import _step1_body, _mailto, _wa_link


def main():
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT notification_id,booking_id,channel,recipient_email,recipient_phone FROM notifications WHERE event LIKE 'step1-%' AND DBMS_LOB.GETLENGTH(body)<=40")
    rows = cur.fetchall(); repaired = 0
    for nid, booking_id, channel, email, phone in rows:
        cur.execute("SELECT booking_id,booking_type,company_name,guest_name_1,guest_email,guest_contact,admin_name,admin_email,admin_contact,pickup_address,pickup_city,pickup_date,pickup_time,drop_address,drop_city,vehicle_type,flight_details,driver_reporting_time FROM bookings WHERE booking_id=:1", (booking_id,))
        row = cur.fetchone()
        if not row: continue
        keys=("booking_id","booking_type","company_name","guest_name_1","guest_email","guest_contact","admin_name","admin_email","admin_contact","pickup_address","pickup_city","pickup_date","pickup_time","drop_address","drop_city","vehicle_type","flight_details","driver_reporting_time")
        body=_step1_body(dict(zip(keys,row)))+"\n\nRentaGO Technologies Pvt. Ltd."
        link=_mailto(email, f"RentaGO Booking Request {booking_id}", body) if channel=='email' else _wa_link(phone, body)
        cur.execute("UPDATE notifications SET subject=:1,body=:2,link=:3,status='Queued',attempts=0,last_attempt=NULL,error_message=NULL WHERE notification_id=:4", (f"RentaGO Booking Request {booking_id}",body,link,nid))
        repaired += 1
    conn.commit(); conn.close(); print(f"Repaired {repaired} blank Step 1 notifications")


if __name__ == '__main__': main()
