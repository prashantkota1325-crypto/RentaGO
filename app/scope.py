"""Role/data scoping for shared records (bookings, trips, invoices).

Account model (user types)
---------------------------
1. RentaGO User (Super Admin / HQ / CEO / Operations / departmental staff)
   -> FULL data access. Which modules they can open is governed by the ROLES
      matrix (sheet x role), handled separately by nav/has_access.
2. Guest            -> only their own bookings/trips/invoices (identity match).
3. Admin            -> corporate admin role: sees their company's employees' records.
4. Vendor           -> sees bookings/trips/invoices for their own vendor.
5. Driver           -> sees trips/bookings assigned to them by driver identity.

For a non-operator user we compute the set of visible booking_ids; trips and
invoices hang off booking_id so the same set applies to all three modules.
"""

OPERATOR_ROLES = {
    "super admin", "superadmin", "hq", "ceo", "operations",
}

CORPORATE_PORTAL_ROLES = {
    "corporate admin", "corporate booking user", "corporate manager", "corporate viewer",
}

VENDOR_PORTAL_ROLES = {
    "vendor", "vendor admin", "vendor operations", "vendor viewer",
}


def _norm(v):
    return (v or "").strip().lower()


def is_internal_user(user):
    """Return whether the authenticated user is an internal RentaGO user."""
    role = _norm(user.get("role"))
    return role in OPERATOR_ROLES or (
        role not in CORPORATE_PORTAL_ROLES | VENDOR_PORTAL_ROLES | {"guest", "driver"}
        and _norm(user.get("organization_type")) == "rentago"
    )


def authorization_tenant(user):
    """Return the authenticated tenant for externally scoped users.

    Missing or ambiguous membership is represented by None and must fail closed.
    Internal RentaGO users are intentionally handled by their existing broad
    operator scope.
    """
    if is_internal_user(user):
        return None
    tenant_id = str(user.get("tenant_id") or "").strip()
    return tenant_id or None


def user_scope(user):
    """Return a scope dict describing the user's data visibility."""
    role = _norm(user.get("role"))
    if is_internal_user(user):
        return {"mode": "all"}
    if role in CORPORATE_PORTAL_ROLES | VENDOR_PORTAL_ROLES | {"guest", "driver"} \
            and not authorization_tenant(user):
        return {"mode": "denied", "user": user}
    if role in CORPORATE_PORTAL_ROLES:
        return {"mode": "company", "user": user}
    if role in VENDOR_PORTAL_ROLES:
        return {"mode": "vendor", "user": user}
    if role == "driver":
        return {"mode": "driver", "user": user}
    return {"mode": "guest", "user": user}


def resolve_company(user):
    """Resolve the user's company as {'id':..., 'name':...} by name lookup."""
    name = _norm(user.get("company")) or _norm(user.get("company_name"))
    if not name:
        return None
    from .db import get_connection
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT company_id, company_name FROM companies "
        "WHERE UPPER(TRIM(company_name))=UPPER(TRIM(:1))",
        (name,),
    )
    row = cur.fetchone()
    conn.close()
    if row:
        return {"id": str(row[0]), "name": row[1]}
    return {"id": None, "name": name}


def _matches_guest(b, user):
    """Booking belongs to a guest by identity match."""
    gnames = {_norm(x) for x in
              (b.get("guest_name_1"), b.get("guest_name_2"), b.get("guest_name_3"),
               b.get("guest_name_4"), b.get("guest_name_5")) if x}
    uname = _norm(user.get("name"))
    uemail = _norm(user.get("email"))
    umobile = _norm(user.get("mobile"))
    uemp = _norm(user.get("emp_id"))
    uid = _norm(user.get("user_id"))
    if (uemp or uid) and b.get("emp_guest_id") and _norm(b.get("emp_guest_id")) in {uemp, uid}:
        return True
    matches = [
        bool(uname and uname in gnames),
        bool(uemail and uemail == _norm(b.get("guest_email"))),
        bool(umobile and umobile == _norm(b.get("guest_contact"))),
    ]
    return sum(matches) >= 2


def _matches_driver(b, user):
    """Booking whose assigned driver is this user."""
    uname = _norm(user.get("name"))
    umobile = _norm(user.get("mobile"))
    uemp = _norm(user.get("emp_id"))
    matches = [
        bool(uname and _norm(b.get("driver_name")) == uname),
        bool(umobile and _norm(b.get("driver_contact")) == umobile),
        bool(uemp and _norm(b.get("driver_name")).find(uemp) != -1),
    ]
    return sum(matches) >= 2


def _matches_vendor(b, user):
    """Booking handled by the authenticated vendor organization."""
    org_id = _norm(user.get("organization_id"))
    return org_id.startswith("vend-") and _norm(b.get("vendor_id")) == org_id[5:]


def _matches_company(b, user):
    """Booking belonging to the authenticated corporate organization."""
    org_id = _norm(user.get("organization_id"))
    if not org_id.startswith("corp-"):
        return False
    company_id = org_id[5:]
    return _norm(b.get("corporate_id")) == company_id or _norm(b.get("company_id")) == company_id


def visible_booking_ids(user, cur):
    """Return set of visible booking_ids, or None meaning 'ALL'."""
    scope = user_scope(user)
    if scope["mode"] == "denied":
        return set()
    if scope["mode"] == "all":
        return None
    tenant_id = authorization_tenant(user)
    if not tenant_id:
        return set()
    tenant_clause = " WHERE tenant_id=:1"
    cur.execute(
        "SELECT booking_id, company_name, company_id, corporate_id, vendor_id, emp_guest_id, "
        "guest_name_1, guest_name_2, guest_name_3, guest_name_4, guest_name_5, "
        "guest_email, guest_contact, admin_name, admin_email, admin_contact, "
        "vendor_name, driver_name, driver_contact "
        "FROM bookings" + tenant_clause,
        (tenant_id,),
    )
    ids = set()
    for r in cur.fetchall():
        b = {
            "company_name": r[1], "company_id": r[2], "corporate_id": r[3], "vendor_id": r[4], "emp_guest_id": r[5],
            "guest_name_1": r[6], "guest_name_2": r[7], "guest_name_3": r[8],
            "guest_name_4": r[9], "guest_name_5": r[10],
            "guest_email": r[11], "guest_contact": r[12],
            "admin_name": r[13], "admin_email": r[14], "admin_contact": r[15],
            "vendor_name": r[16], "driver_name": r[17], "driver_contact": r[18],
        }
        u = scope["user"]
        mode = scope["mode"]
        if mode == "company":
            ok = _matches_company(b, u)
        elif mode == "vendor":
            ok = _matches_vendor(b, u)
        elif mode == "driver":
            ok = _matches_driver(b, u)
        else:
            ok = _matches_guest(b, u)
        if ok:
            ids.add(r[0])
    return ids


def can_view(visible_ids, booking_id):
    """True when visible_ids is None (ALL) or booking_id is in the set."""
    if visible_ids is None:
        return True
    return booking_id in visible_ids
