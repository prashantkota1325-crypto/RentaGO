"""Invoice routes: list, invoice detail, vendor expense submission, and print view."""

from datetime import datetime
from pathlib import Path
import os
import uuid

from fastapi import APIRouter, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates

from ..auth import current_user, module_level
from ..templating import templates
from ..db import get_connection
from ..scope import visible_booking_ids, can_view, OPERATOR_ROLES
from ..gps import gps_report, SYNC_THRESHOLD_METERS
from ..audit import audit
from ..sla_engine import emit_start, complete_for_entity

router = APIRouter(prefix="/invoices")


def _vendor_role(user):
    return (user or {}).get("role", "").strip().lower() in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}

# Roles allowed to submit vendor expenses / finalize invoices.
EXPENSE_ROLES = set(OPERATOR_ROLES) | {
    "finance", "vendor manager", "vendor", "vendor admin", "vendor operations",
}
ATTACHMENT_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx", ".xls", ".xlsx"}
ATTACHMENT_ROOT = Path("app/uploads/invoice_expenses")


@router.get("")
def list_invoices(request: Request, status: str = "", q: str = ""):
    """List invoices, optionally filtered by status and/or booking/guest text."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if _vendor_role(user):
        return RedirectResponse(url="/dashboards/vendor?msg=client-invoices-hidden", status_code=303)
    if module_level(user, "Invoices") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    sql = (
        "SELECT invoice_id, booking_id, "
        "(SELECT MIN(t.trip_id) FROM trips t WHERE t.booking_id=invoices.booking_id), "
        "(SELECT MIN(vi.invoice_number) FROM vendor_invoices vi WHERE vi.booking_id=invoices.booking_id), "
        "guest_name, company_name, pickup_date, "
        "invoice_status, payment_status, original_amount, final_amount "
        "FROM invoices"
    )
    params = []
    conds = []
    if (user.get("role") or "").strip().lower() in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}:
        params.append(user.get("company_name") or user.get("company") or "")
        conds.append(f"EXISTS (SELECT 1 FROM bookings vb WHERE vb.booking_id=invoices.booking_id AND UPPER(TRIM(vb.vendor_name))=UPPER(TRIM(:{len(params)})))")
    if user.get("tenant_id") and (user.get("role") or "").strip().lower() != "super admin":
        params.append(user["tenant_id"]); conds.append(f"invoices.tenant_id=:{len(params)}")
    if status:
        params.append("%" + status + "%")
        conds.append("UPPER(invoice_status) LIKE UPPER(:" + str(len(params)) + ")")
    if q:
        params.append("%" + q + "%")
        conds.append("(LOWER(guest_name) LIKE LOWER(:" + str(len(params)) + ") OR "
                     "LOWER(booking_id) LIKE LOWER(:" + str(len(params)) + "))")
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY invoice_id DESC FETCH FIRST 500 ROWS ONLY"
    cur.execute(sql, params)
    rows = cur.fetchall()

    visible = visible_booking_ids(user, cur)
    conn.close()

    invoices = []
    for r in rows:
        if not can_view(visible, str(r[1])):
            continue
        invoices.append({
            "invoice_id": r[0], "booking_id": r[1], "trip_id": r[2], "vendor_invoice": r[3], "guest_name": r[4],
            "company_name": r[5], "pickup_date": r[6], "invoice_status": r[7],
            "payment_status": r[8], "original_amount": r[9], "final_amount": r[10],
        })
    return templates.TemplateResponse(
        "invoices/list.html",
        {"request": request, "user": user, "invoices": invoices,
         "status_filter": status, "query": q},
    )


@router.get("/{invoice_id}")
def invoice_detail(request: Request, invoice_id: str):
    """Show full details of a single invoice."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if _vendor_role(user):
        return RedirectResponse(url="/dashboards/vendor?msg=client-invoices-hidden", status_code=303)
    if module_level(user, "Invoices") is None:
        return RedirectResponse(url="/home?msg=access-denied", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM invoices WHERE invoice_id=:1", (invoice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return templates.TemplateResponse(
            "invoices/not_found.html", {"request": request, "user": user}
        )
    cols = [d[0].lower() for d in cur.description]
    data = dict(zip(cols, row))
    if (user.get("tenant_id") and (user.get("role") or "").strip().lower() != "super admin"
            and str(data.get("tenant_id") or "") != str(user["tenant_id"])):
        conn.close()
        return templates.TemplateResponse("invoices/not_found.html", {"request": request, "user": user})
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(data.get("booking_id") or "")):
        conn.close()
        return templates.TemplateResponse(
            "invoices/not_found.html", {"request": request, "user": user}
        )
    if (user.get("role") or "").strip().lower() in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}:
        cur.execute("SELECT vendor_name FROM bookings WHERE booking_id=:1", (data.get("booking_id"),))
        vendor_row = cur.fetchone()
        if not vendor_row or str(vendor_row[0] or "").strip().lower() != str(user.get("company_name") or user.get("company") or "").strip().lower():
            conn.close()
            return templates.TemplateResponse("invoices/not_found.html", {"request": request, "user": user})
    cur.execute(
        "SELECT payment_id, pay_type, pay_date, amount, pay_method, pay_status "
        "FROM payments WHERE ref_id=:1 ORDER BY payment_id",
        (invoice_id,),
    )
    payments = [dict(zip(
        ("payment_id", "pay_type", "pay_date", "amount", "pay_method",
         "pay_status"), r)) for r in cur.fetchall()]
    cur.execute(
        "SELECT attachment_id, file_name, content_type, uploaded_by, uploaded_dt "
        "FROM invoice_expense_documents WHERE invoice_id=:1 ORDER BY uploaded_dt DESC",
        (invoice_id,))
    attachments = [dict(zip(("attachment_id", "file_name", "content_type",
                             "uploaded_by", "uploaded_dt"), r)) for r in cur.fetchall()]
    conn.close()
    can_submit = (
        (data.get("payment_status") or "").strip() != "Final Invoice Sent"
        and (data.get("invoice_status") or "").strip() != "Cancellation Invoice"
        and (user.get("role") or "").strip().lower() in EXPENSE_ROLES
    )
    can_pay = module_level(user, "Payments") == "F"
    return templates.TemplateResponse(
        "invoices/detail.html",
        {"request": request, "user": user, "inv": data, "can_submit": can_submit,
         "payments": payments, "attachments": attachments, "can_pay": can_pay},
    )


@router.post("/{invoice_id}/submit-expenses")
def submit_expenses(
    request: Request,
    invoice_id: str,
    toll: str = Form("0"),
    parking: str = Form("0"),
    extra_kms: str = Form("0"),
    extra_hours: str = Form("0"),
    other_expenses: str = Form("0"),
):
    """Mirrors the trip-expense submission and final-invoice workflow.

    Stores the vendor-reported expense amounts, computes total, and flips the
    invoice to 'Final Invoice'. finalAmount == total vendor expenses.
    """
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if _vendor_role(user):
        return RedirectResponse(url="/dashboards/vendor?msg=vendor-billing-separate", status_code=303)
    if (user.get("role") or "").strip().lower() not in EXPENSE_ROLES:
        return RedirectResponse(url=f"/invoices/{invoice_id}?msg=not-allowed",
                                status_code=303)

    vals = {}
    for name, raw in (("toll", toll), ("parking", parking), ("extra_kms", extra_kms),
                      ("extra_hours", extra_hours), ("other_expenses", other_expenses)):
        try:
            vals[name] = float(raw or 0)
        except ValueError:
            return RedirectResponse(url=f"/invoices/{invoice_id}?msg=invalid", status_code=303)
        if vals[name] < 0:
            return RedirectResponse(url=f"/invoices/{invoice_id}?msg=invalid", status_code=303)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM invoices WHERE invoice_id=:1", (invoice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return RedirectResponse(url="/invoices", status_code=303)
    cols = [d[0].lower() for d in cur.description]
    inv = dict(zip(cols, row))
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(inv.get("booking_id") or "")):
        conn.close()
        return RedirectResponse(url=f"/invoices/{invoice_id}?msg=not-allowed",
                                status_code=303)

    if (inv.get("payment_status") or "").strip() == "Final Invoice Sent":
        conn.close()
        return RedirectResponse(url=f"/invoices/{invoice_id}?msg=already-final", status_code=303)

    total = sum(vals.values())
    now = datetime.now()
    # Get original_amount from the invoice to include in final bill
    cur.execute("SELECT original_amount FROM invoices WHERE invoice_id=:1", (invoice_id,))
    orig_row = cur.fetchone()
    try:
        original_amount = float(orig_row[0] or 0) if orig_row else 0.0
    except (TypeError, ValueError):
        original_amount = 0.0
    grand_total = total + original_amount
    cur.execute(
        "UPDATE invoices SET toll=:1, parking=:2, extra_kms=:3, extra_hours=:4, "
        "other_expenses=:5, total_vendor_expenses=:6, vendor_submitted_on=:7, "
        "final_amount=:8, invoice_status='Final Invoice', payment_status='Final Invoice Sent', "
        "final_invoice_sent_on=:7 WHERE invoice_id=:9",
        (vals["toll"], vals["parking"], vals["extra_kms"], vals["extra_hours"],
         vals["other_expenses"], total, now, grand_total, invoice_id),
    )
    # refresh the invoice dict for the notification payload
    cur.execute("SELECT * FROM invoices WHERE invoice_id=:1", (invoice_id,))
    irow = cur.fetchone()
    icols = [d[0].lower() for d in cur.description]
    inv_data = dict(zip(icols, irow)) if irow else dict(inv)
    booking = None
    bid = inv_data.get("booking_id")
    if bid:
        cur.execute("SELECT * FROM bookings WHERE booking_id=:1", (bid,))
        brow = cur.fetchone()
        if brow:
            bcols = [d[0].lower() for d in cur.description]
            booking = dict(zip(bcols, brow))
    from .. import notify
    notify.notify_final_invoice(conn, user, inv_data, booking or {})
    if bid:
        complete_for_entity(conn, "BOOKING", bid, ("TRIP_COMPLETED",), "Final invoice sent")
    emit_start(conn, "INVOICE_FINAL_SENT", "INVOICE", invoice_id, department="Finance",
               context={"corporate_id": (booking or {}).get("company_id"),
                        "booking_type": (booking or {}).get("booking_type"),
                        "policy_category": "Finance"})
    audit(conn, user, "Vendor Expenses Submitted (Final Invoice)", invoice_id,
          f"total Rs.{total:.2f}")
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/invoices/{invoice_id}?msg=final", status_code=303)


@router.post("/{invoice_id}/expense-attachments")
async def upload_expense_attachment(request: Request, invoice_id: str,
                                    attachment: UploadFile = File(...)):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if _vendor_role(user):
        return RedirectResponse(url="/dashboards/vendor?msg=vendor-billing-separate", status_code=303)
    if (user.get("role") or "").strip().lower() not in EXPENSE_ROLES:
        return RedirectResponse(url=f"/invoices/{invoice_id}?msg=not-allowed", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT booking_id, payment_status, tenant_id FROM invoices WHERE invoice_id=:1", (invoice_id,))
    row = cur.fetchone()
    visible = visible_booking_ids(user, cur)
    if not row or not can_view(visible, str(row[0] or "")) or (user.get("tenant_id") and (user.get("role") or "").strip().lower() != "super admin" and str(row[2] or "") != str(user["tenant_id"])):
        conn.close()
        return RedirectResponse(url="/invoices", status_code=303)
    if row[1] == "Final Invoice Sent":
        conn.close()
        return RedirectResponse(url=f"/invoices/{invoice_id}?msg=already-final", status_code=303)
    suffix = Path(attachment.filename or "").suffix.lower()
    if suffix not in ATTACHMENT_EXTENSIONS:
        conn.close()
        return RedirectResponse(url=f"/invoices/{invoice_id}?msg=attachment-invalid", status_code=303)
    storage_name = f"{uuid.uuid4().hex}{suffix}"
    ATTACHMENT_ROOT.mkdir(parents=True, exist_ok=True)
    target = ATTACHMENT_ROOT / storage_name
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := await attachment.read(1024 * 1024):
                size += len(chunk)
                if size > 10 * 1024 * 1024:
                    raise ValueError("file too large")
                out.write(chunk)
    except Exception:
        if target.exists():
            target.unlink()
        conn.close()
        return RedirectResponse(url=f"/invoices/{invoice_id}?msg=attachment-invalid", status_code=303)
    attachment_id = f"DOC-{uuid.uuid4().hex[:20]}"
    cur.execute(
        "INSERT INTO invoice_expense_documents (attachment_id, tenant_id, invoice_id, file_name, "
        "storage_name, content_type, uploaded_by, uploaded_dt) VALUES (:1,:2,:3,:4,:5,:6,:7,:8)",
        (attachment_id, row[2] or user.get("tenant_id") or "TEN-RENTA-GO", invoice_id, (attachment.filename or "attachment")[:255],
          storage_name, attachment.content_type, user["user_id"], datetime.now()),
    )
    audit(conn, user, "Trip Expense Attachment Uploaded", invoice_id,
          f"attachment={attachment_id}; size={size}")
    conn.commit()
    conn.close()
    return RedirectResponse(url=f"/invoices/{invoice_id}?msg=attachment-uploaded", status_code=303)


@router.get("/{invoice_id}/expense-attachments/{attachment_id}")
def download_expense_attachment(request: Request, invoice_id: str, attachment_id: str):
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if _vendor_role(user):
        return RedirectResponse(url="/dashboards/vendor?msg=vendor-billing-separate", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT i.booking_id, d.file_name, d.storage_name, d.tenant_id FROM invoice_expense_documents d "
        "JOIN invoices i ON i.invoice_id=d.invoice_id WHERE d.invoice_id=:1 AND d.attachment_id=:2",
        (invoice_id, attachment_id))
    row = cur.fetchone()
    visible = visible_booking_ids(user, cur)
    if not row or not can_view(visible, str(row[0] or "")) or (user.get("tenant_id") and (user.get("role") or "").strip().lower() != "super admin" and str(row[3] or "") != str(user["tenant_id"])):
        conn.close()
        return RedirectResponse(url="/invoices", status_code=303)
    cur.execute("SELECT uploaded_by FROM invoice_expense_documents WHERE attachment_id=:1", (attachment_id,))
    audit(conn, user, "Trip Expense Attachment Downloaded", invoice_id, f"attachment={attachment_id}")
    conn.commit()
    conn.close()
    path = ATTACHMENT_ROOT / row[2]
    if not path.is_file():
        return RedirectResponse(url=f"/invoices/{invoice_id}?msg=attachment-missing", status_code=303)
    return FileResponse(path, filename=row[1])


@router.get("/{invoice_id}/print")
def print_invoice(request: Request, invoice_id: str):
    """Render a print/PDF-friendly A4 invoice (provisional or final)."""
    user = current_user(request)
    if not user:
        return RedirectResponse(url="/auth/login", status_code=303)
    if _vendor_role(user):
        return RedirectResponse(url="/dashboards/vendor?msg=client-invoices-hidden", status_code=303)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM invoices WHERE invoice_id=:1", (invoice_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        return templates.TemplateResponse(
            "invoices/not_found.html", {"request": request, "user": user}
        )
    cols = [d[0].lower() for d in cur.description]
    data = dict(zip(cols, row))
    if (user.get("tenant_id") and (user.get("role") or "").strip().lower() != "super admin" and str(data.get("tenant_id") or "") != str(user["tenant_id"])):
        conn.close(); return templates.TemplateResponse("invoices/not_found.html", {"request": request, "user": user})
    visible = visible_booking_ids(user, cur)
    if not can_view(visible, str(data.get("booking_id") or "")):
        conn.close()
        return templates.TemplateResponse(
            "invoices/not_found.html", {"request": request, "user": user}
        )
    if (user.get("role") or "").strip().lower() in {"vendor", "vendor admin", "vendor operations", "vendor viewer"}:
        cur.execute("SELECT vendor_name FROM bookings WHERE booking_id=:1", (data.get("booking_id"),))
        vendor_row = cur.fetchone()
        if not vendor_row or str(vendor_row[0] or "").strip().lower() != str(user.get("company_name") or user.get("company") or "").strip().lower():
            conn.close(); return templates.TemplateResponse("invoices/not_found.html", {"request": request, "user": user})
    booking = None
    trip = None
    gps = {"driver": "", "guest": "", "status": "Not captured", "distance_m": None,
           "threshold": SYNC_THRESHOLD_METERS}
    bid = data.get("booking_id")
    if bid:
        try:
            cur.execute("SELECT * FROM bookings WHERE booking_id=:1", (bid,))
            brow = cur.fetchone()
            if brow:
                bcols = [d[0].lower() for d in cur.description]
                booking = dict(zip(bcols, brow))
                gps = gps_report(
                    booking.get("driver_live_location"),
                    booking.get("guest_live_location"),
                    booking.get("location_sync"),
                )
        except Exception:
            booking = None
        try:
            cur.execute("SELECT * FROM trips WHERE booking_id=:1", (bid,))
            trow = cur.fetchone()
            if trow:
                tcols = [d[0].lower() for d in cur.description]
                trip = dict(zip(tcols, trow))
                gps = gps_report(
                    trip.get("driver_live_location"),
                    trip.get("guest_live_location"),
                    trip.get("location_sync"),
                )
        except Exception:
            trip = None
    conn.close()
    return templates.TemplateResponse(
        "invoices/print.html",
        {"request": request, "user": user, "inv": data, "b": booking, "t": trip,
         "gps": gps},
    )
