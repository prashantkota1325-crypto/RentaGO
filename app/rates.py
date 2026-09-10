"""Ratecard pricing lookup (RateCards sheet port).

The imported ratecards rows carry:
  rate_card_id, company_id ('DEFAULT' or a real company id), category (vehicle
  category), package_rate = Package Rate (Customer Rate), extra_hr_rate = Extra Hr Rate, extra_km_rate = Extra KM Rate.

`customer_rate` resolves the best match for a booking: the company's own card
first, then the DEFAULT card, matching the vehicle category loosely.
"""

from .db import get_connection


def customer_rate(company_id, vehicle_type) -> float:
    """Best-effort customer rate for a booking. 0.0 when no card matches."""
    company_id = (company_id or "").strip().upper()
    vehicle_type = (vehicle_type or "").strip()
    if not vehicle_type:
        return 0.0
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT company_id, category, package_rate FROM ratecards "
            "WHERE UPPER(category) LIKE UPPER(:1)",
            ("%" + vehicle_type + "%",),
        )
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()

    def match(cid):
        c = (cid or "").strip().upper()
        if company_id and c == company_id:
            return 2
        if c == "DEFAULT":
            return 1
        return 0

    best, best_rank = 0.0, 0
    for cid, _cat, price in rows:
        rank = match(cid)
        if rank > best_rank:
            try:
                best = float(price or 0)
                best_rank = rank
            except (TypeError, ValueError):
                continue
    return best
