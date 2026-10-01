def can_view_booking_kpis(user):
    return (user or {}).get("role", "").strip().lower() not in {
        "corporate admin", "corporate booking user", "corporate manager", "corporate viewer",
        "vendor", "vendor admin", "vendor operations", "vendor viewer", "guest", "driver",
    }


def booking_trip_kpis(cur, user, sla_breached=0):
    tenant = user.get("tenant_id"); role = (user.get("role") or "").lower()
    where = ""; params = []
    if tenant and role != "super admin": params.append(tenant); where = " WHERE tenant_id=:1"
    cur.execute("SELECT COUNT(*),SUM(CASE WHEN status_reason='Trip Completed' THEN 1 ELSE 0 END),SUM(CASE WHEN booking_status LIKE '3-%' OR status_reason LIKE '%Cancelled%' THEN 1 ELSE 0 END),SUM(CASE WHEN booking_status LIKE '1-%' OR status_reason LIKE '%Pending%' THEN 1 ELSE 0 END),SUM(CASE WHEN booking_status NOT LIKE '3-%' AND status_reason<>'Trip Completed' AND TRUNC(pickup_date)=TRUNC(SYSDATE) THEN 1 ELSE 0 END),SUM(CASE WHEN status_reason='Trip In Progress' THEN 1 ELSE 0 END) FROM bookings"+where, params or None)
    r=cur.fetchone(); extra=(where+(' AND ' if where else ' WHERE ')); cur.execute("SELECT COUNT(*) FROM bookings"+extra+"TRUNC(pickup_date)=TRUNC(SYSDATE) AND REGEXP_LIKE(TRIM(pickup_time),'^[0-9]{1,2}:[0-9]{2}$') AND CASE WHEN REGEXP_LIKE(TRIM(pickup_time),'^[0-9]{1,2}:[0-9]{2}$') THEN TO_DATE(TO_CHAR(pickup_date,'YYYY-MM-DD')||' '||TRIM(pickup_time),'YYYY-MM-DD HH24:MI') END BETWEEN SYSDATE AND SYSDATE+(2/24)",params or None)
    pickups = int(cur.fetchone()[0] or 0)
    cur.execute("SELECT COUNT(*) FROM bookings"+extra+"TRUNC(pickup_date)=TRUNC(SYSDATE) AND booking_status NOT LIKE '3-%' AND status_reason NOT IN ('Trip In Progress','Trip Completed') AND REGEXP_LIKE(TRIM(pickup_time),'^[0-9]{1,2}:[0-9]{2}$') AND TO_DATE(TO_CHAR(pickup_date,'YYYY-MM-DD')||' '||TRIM(pickup_time),'YYYY-MM-DD HH24:MI') < SYSDATE",params or None)
    passed = int(cur.fetchone()[0] or 0)
    return dict(zip(('total','completed','cancelled','pending','current','in_progress'),[int(x or 0) for x in r])) | {'current_pending':int(r[3] or 0),'pickups_2h':pickups,'pickup_passed':passed,'sla_breached':int(sla_breached or 0)}
