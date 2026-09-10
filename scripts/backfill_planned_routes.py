"""Backfill ordered multi-stop route payloads for legacy bookings."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import get_connection
from app.routes.bookings import _planned_stops, _planned_route_payload, _sync_trip_booking_details
from app.gps import route_estimate_multi


def main():
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "SELECT booking_id,pickup_address,pickup_city,pickup_state,pickup_gps, "
        "pickup_1,pickup_2,pickup_3,pickup_4,pickup_5,drop_address,drop_city,drop_state,drop_gps, "
        "drop_1,drop_2,drop_3,drop_4,drop_5,planned_route_json FROM bookings")
    updated = 0
    for row in cur.fetchall():
        if row[19]:
            try:
                if json.loads(str(row[19])).get("stops"):
                    continue
            except (TypeError, ValueError, AttributeError):
                pass
        if not any(row[i] for i in (5, 6, 7, 8, 9, 14, 15, 16, 17, 18)):
            continue
        stops = _planned_stops(row[1], row[2], row[3], "India", row[4],
                               [(row[i], "") for i in (5, 6, 7, 8, 9)],
                               row[10], row[11], row[12], "India", row[13],
                               [(row[i], "") for i in (14, 15, 16, 17, 18)])
        kms, hours, source, legs = route_estimate_multi(stops)
        payload = _planned_route_payload(stops, legs)
        cur.execute("UPDATE bookings SET planned_kms=:1, planned_hrs=:2, planned_route_source=:3, planned_route_json=:4 WHERE booking_id=:5",
                    (kms, hours, source, payload, row[0]))
        _sync_trip_booking_details(conn, {"booking_id": row[0], "guest_name_1": None,
                                          "pickup_date": None, "pickup_address": row[1],
                                          "drop_address": row[10], "planned_route_json": payload})
        updated += 1
        print(f"{row[0]}: {kms} km, {len(legs)} legs, {source}")
    conn.commit(); conn.close()
    print(f"Updated {updated} legacy multi-stop bookings")


if __name__ == "__main__":
    main()
