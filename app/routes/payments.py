"""Payment routes: list, record payments against invoices/trips (Payments port)."""

from datetime import datetime

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from ..auth import current_user, module_level
from ..templating import templates
from ..db import get_connection
from ..scope import visible_booking_ids, can_view, OPERATOR_ROLES
from ..audit import audit
from ..sla_engine import emit_start, complete_for_entity

router = APIRouter(prefix="/payments")

PAY_TYPES = ("Receipt from Customer", "Payment to Vendor", "Refund to Customer")
PAY_METHODS = ("UPI", "NEFT", "RTGS", "IMPS", "Cheque", "Cash", "Card", "Adjustment")
EXPENSE_ROLES = set(OPERATOR_ROLES) | {"finance", "vendor manager", "vendor"}


def _can_record(user):
    role = (user.get("role") or "").strip().lower()
    return role in EXPENSE_ROLES


def _next_payment_id(conn):
    """Next payment id continuing the PY-0001 convention."""
    cur = conn.cursor()
    cur.execute("SELECT payment_id FROM payments")
    max_num = 0
    for (pid,) in cur.fetchall():
        s = str(pid or "").strip()
        if s.upper().startswith("PY-"):
            try:
                n = int(s[3:])
                if n > max_num:
                    max_num = n
            except Exception:
                pass
    return "PY-%04d" % (max_num + 1)


def _visible_payment_rows(user, cur, rows):
    """Filter payment rows by the user's booking visibility."""
    visible = visible_booking_ids(user, cur)
    if visible is None:
        return rows
    # Map invoice -> booking for scoping.
    cur.execute("SELECT invoice_id, booking_id FROM invoices")
    inv_map = {str(r[0]): str(r[1]) for r in cur.fetchall()}
    out = []
    for r in rows:
        ref = str(r[4] or "")
        if ref in inv_map and can_view(visible, inv_map[ref]):
            out.append(r)
    return out


@router.get("")
def list_payments(request: Request, pay_type: str = "", q: str = ""):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if module_level(user, "Payments") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    sql = (
        "SELECT payment_id, pay_type, pay_date, ref_id, counterparty, amount, "
        "pay_method, pay_status, notes FROM payments"
    )
    params, conds = [], []
    if pay_type:
        params.append("%" + pay_type + "%")
        conds.append("UPPER(pay_type) LIKE UPPER(:" + str(len(params)) + ")")
    if q:
        params.append("%" + q + "%")
        conds.append("(LOWER(counterparty) LIKE LOWER(:" + str(len(params))
                     + ") OR LOWER(ref_id) LIKE LOWER(:" + str(len(params)) + "))")
    if user.get("tenant_id") and (user.get("role") or "").strip().lower() != "super admin":
        params.append(user["tenant_id"]); conds.append(f"tenant_id=:{len(params)}")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY payment_id DESC FETCH FIRST 500 ROWS ONLY"
    cur.execute(sql, params)
    rows = cur.fetchall()
    rows = _visible_payment_rows(user, cur, rows)
    conn.close()
    payments = [{
        "payment_id": r[0], "pay_type": r[1], "pay_date": r[2], "ref_id": r[3],
        "counterparty": r[4], "amount": r[5], "pay_method": r[6],
        "pay_status": r[7], "notes": r[8],
    } for r in rows]
    return templates.TemplateResponse(
        "payments/list.html",
        {"request": request, "user": user, "payments": payments,
         "type_filter": pay_type, "query": q, "can_record": _can_record(user),
         "pay_types": PAY_TYPES, "pay_methods": PAY_METHODS},
    )


@router.post("/record")
def record_payment(
    request: Request,
    pay_type: str = Form("Receipt from Customer"),
    ref_id: str = Form(""),
    counterparty: str = Form(""),
    amount: str = Form("0"),
    pay_date: str = Form(""),
    pay_method: str = Form("UPI"),
    pay_status: str = Form("Completed"),
    notes: str = Form(""),
):
    """Record a payment; when it references an invoice, update its status."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if module_level(user, "Payments") != "F" or not _can_record(user):
        return RedirectResponse(url="/payments?msg=not-allowed", status_code=303)
    if pay_type not in PAY_TYPES or pay_method not in PAY_METHODS:
        return RedirectResponse(url="/payments?msg=invalid", status_code=303)
    if pay_status not in ("Pending", "Completed", "Failed", "Refunded"):
        return RedirectResponse(url="/payments?msg=invalid", status_code=303)
    try:
        amount_val = float(amount or 0)
    except ValueError:
        return RedirectResponse(url="/payments?msg=invalid", status_code=303)
    if amount_val <= 0 or not (ref_id or "").strip():
        return RedirectResponse(url="/payments?msg=invalid", status_code=303)

    pay_dt = None
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            pay_dt = datetime.strptime((pay_date or "").strip(), fmt).date()
            break
        except Exception:
            continue
    if pay_dt is None:
        pay_dt = datetime.now().date()

    conn = get_connection()
    cur = conn.cursor()
    pid = _next_payment_id(conn)
    cur.execute(
        """INSERT INTO payments (
            payment_id, tenant_id, pay_type, pay_date, ref_id, counterparty, amount,
            pay_method, pay_status, notes
        ) VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10)""",
        (pid, user.get("tenant_id") or "TEN-RENTA-GO", pay_type, pay_dt, ref_id.strip(), counterparty.strip(), amount_val,
         pay_method, pay_status, notes.strip()),
    )

    # Invoice linkage: receipts against an invoice update its payment status.
    target = f"/payments?msg=recorded"
    cur.execute("SELECT invoice_id, booking_id, final_amount, tenant_id FROM invoices "
                "WHERE invoice_id=:1", (ref_id.strip(),))
    inv_row = cur.fetchone()
    if inv_row:
        if user.get("tenant_id") and (user.get("role") or "").strip().lower() != "super admin" and str(inv_row[3] or "") != str(user["tenant_id"]):
            conn.close(); return RedirectResponse(url="/payments?msg=not-allowed", status_code=303)
        visible = visible_booking_ids(user, cur)
        if not can_view(visible, str(inv_row[1] or "")):
            conn.close()
            return RedirectResponse(url="/payments?msg=not-allowed", status_code=303)
    if inv_row and "Receipt" in pay_type:
        inv_id, booking_id, final_amount, _invoice_tenant_id = inv_row
        try:
            final_amt = float(final_amount or 0)
        except (TypeError, ValueError):
            final_amt = 0.0
        status = ("Payment Received" if final_amt and amount_val >= final_amt - 0.01
                  else "Partially Paid")
        cur.execute("UPDATE invoices SET payment_status=:1 WHERE invoice_id=:2",
                    (status, inv_id))
        if status == "Payment Received":
            complete_for_entity(conn, "INVOICE", inv_id, ("INVOICE_FINAL_SENT",), "Payment received")
        target = f"/invoices/{inv_id}?msg=payment-recorded"
    if inv_row and "Refund" in pay_type and pay_status == "Completed":
        complete_for_entity(conn, "INVOICE", inv_row[0], ("REFUND_REQUIRED",), "Refund completed")
    if pay_status == "Completed":
        emit_start(conn, "PAYMENT_RECORDED", "PAYMENT", pid, department="Finance",
                   context={"payment_type": pay_type, "payment_method": pay_method,
                            "reference_id": ref_id.strip(), "policy_category": "Finance"})
    audit(conn, user, "Payment Recorded", pid,
          f"{pay_type} | ref {ref_id.strip()} | Rs.{amount_val:.2f}")
    conn.commit()
    conn.close()
    return RedirectResponse(url=target, status_code=303)
