"""Internal trusted Driver-device provisioning and online validation."""

import base64

from fastapi import APIRouter, Request, Form
from fastapi.responses import JSONResponse

from ..auth import current_user, module_level
from ..audit import audit
from ..db import get_connection
from ..scope import is_internal_user
from ..trusted_devices import (provision_device, validate_device, revoke_device,
                               issue_challenge, issue_offline_authorization)
from ..config import settings
from itsdangerous import URLSafeTimedSerializer

router = APIRouter(prefix="/auth/driver-devices")


def _admin(user):
    return bool(user and is_internal_user(user) and module_level(user, "Users") == "F")


def _driver_binding(cur, user):
    tenant_id = (user.get("tenant_id") or "").strip()
    if not tenant_id:
        return None
    cur.execute(
        "SELECT driver_id,vendor_id,tenant_id FROM drivers WHERE tenant_id=:1 "
        "AND (UPPER(TRIM(driver_name))=UPPER(TRIM(:2)) OR mobile=:3) "
        "AND (status IS NULL OR UPPER(status)='ACTIVE') FETCH FIRST 1 ROWS ONLY",
        (tenant_id, user.get("name") or "", user.get("mobile") or ""),
    )
    row = cur.fetchone()
    return {"driver_id": row[0], "vendor_id": row[1], "tenant_id": row[2]} if row else None


@router.post("/provision")
def provision(request: Request, device_id: str = Form(""), driver_id: str = Form(""),
              tenant_id: str = Form(""), vendor_id: str = Form(""),
              device_key_id: str = Form(""), public_key: str = Form(""),
              algorithm: str = Form("ED25519"),
              offline_days: int = Form(7), device_name: str = Form(""),
              platform: str = Form("Android")):
    user = current_user(request)
    role = (user or {}).get("role", "").strip().lower()
    if role == "driver":
        tenant_id = (user.get("tenant_id") or "").strip()
        if not tenant_id:
            return JSONResponse({"error": "driver tenant unavailable"}, status_code=403)
        conn = get_connection(); cur = conn.cursor()
        cur.execute(
            "SELECT driver_id,vendor_id,tenant_id FROM drivers WHERE tenant_id=:1 "
            "AND (UPPER(TRIM(driver_name))=UPPER(TRIM(:2)) OR mobile=:3) "
            "AND (status IS NULL OR UPPER(status)='ACTIVE') FETCH FIRST 1 ROWS ONLY",
            (tenant_id, user.get("name") or "", user.get("mobile") or ""),
        )
        driver = cur.fetchone()
        if not driver:
            conn.close(); return JSONResponse({"error": "driver master record not found"}, status_code=403)
        driver_id, vendor_id, tenant_id = driver
        provision_user = user
    elif _admin(user):
        conn = get_connection(); cur = conn.cursor()
        if not all((driver_id.strip(), tenant_id.strip(), device_id.strip(), public_key.strip(), device_key_id.strip())):
            conn.close(); return JSONResponse({"error": "required fields missing"}, status_code=400)
        cur.execute("SELECT vendor_id,tenant_id FROM drivers WHERE driver_id=:1 AND tenant_id=:2 AND (status IS NULL OR UPPER(status)='ACTIVE')",
                    (driver_id.strip(), tenant_id.strip()))
        driver = cur.fetchone()
        if not driver or (vendor_id.strip() and str(driver[0] or '') != vendor_id.strip()):
            conn.close(); return JSONResponse({"error": "driver/tenant/vendor mismatch"}, status_code=403)
        driver_id, vendor_id, tenant_id = driver[0], driver[0], driver[1]
        provision_user = user
    else:
        return JSONResponse({"error": "not authorized"}, status_code=403)
    if not all((device_id.strip(), driver_id.strip(), tenant_id.strip(), public_key.strip(), device_key_id.strip())):
        conn.close(); return JSONResponse({"error": "required fields missing"}, status_code=400)
    try:
        algorithm = algorithm.strip().upper()
        if algorithm not in {"ED25519", "ECDSA_P256_SHA256"}:
            raise ValueError("unsupported trusted-device algorithm")
        provision_device(conn, device_id.strip(), driver_id.strip(), str(tenant_id), vendor_id,
                         device_key_id.strip(), public_key.strip(), provision_user.get("user_id"),
                         offline_days, device_name, platform, algorithm)
    except (ValueError, TypeError) as exc:
        conn.close(); return JSONResponse({"error": str(exc)}, status_code=400)
    audit(conn, provision_user, "DEVICE_PROVISIONED", device_id, f"driver_id={driver_id.strip()}; tenant={tenant_id}")
    conn.commit(); conn.close()
    return JSONResponse({"ok": True, "device_id": device_id.strip(), "status": "OFFLINE_AUTHORIZED"})


@router.post("/validate")
async def validate(request: Request):
    user = current_user(request)
    if not user or (user.get("role") or '').strip().lower() != 'driver':
        return JSONResponse({"error": "driver session required"}, status_code=403)
    data = await request.json()
    device_id = str(data.get("device_id") or "")
    device_key_id = str(data.get("device_key_id") or "")
    payload = data.get("payload")
    signature = data.get("signature")
    if not device_id or not device_key_id:
        return JSONResponse({"error": "device_id and device_key_id required"}, status_code=400)
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "SELECT driver_id,vendor_id,tenant_id FROM drivers WHERE tenant_id=:1 "
        "AND (UPPER(TRIM(driver_name))=UPPER(TRIM(:2)) OR mobile=:3) "
        "AND (status IS NULL OR UPPER(status)='ACTIVE') FETCH FIRST 1 ROWS ONLY",
        (user.get("tenant_id"), user.get("name") or "", user.get("mobile") or ""),
    )
    driver = cur.fetchone()
    if not driver:
        conn.close(); return JSONResponse({"authorized": False, "state": "DRIVER_NOT_PROVISIONED"}, status_code=403)
    state = validate_device(cur, device_id, driver[0], driver[2], driver[1], device_key_id, payload, signature)
    if state != "OFFLINE_AUTHORIZED":
        conn.commit(); conn.close(); return JSONResponse({"authorized": False, "state": state}, status_code=403)
    conn.commit(); conn.close()
    return JSONResponse({"authorized": True, "state": state})


@router.post("/challenge")
def challenge(request: Request, device_id: str = Form("")):
    user = current_user(request)
    if not user or (user.get("role") or "").strip().lower() != "driver":
        return JSONResponse({"error": "driver session required"}, status_code=403)
    conn = get_connection(); cur = conn.cursor()
    binding = _driver_binding(cur, user)
    if not binding:
        conn.close(); return JSONResponse({"error": "driver binding unavailable"}, status_code=403)
    cur.execute("SELECT device_id,driver_id,tenant_id,vendor_id,status,offline_authorized_until FROM trusted_driver_devices WHERE device_id=:1",
                (device_id.strip(),))
    row = cur.fetchone()
    if not row or str(row[1]) != str(binding["driver_id"]) or str(row[2]) != str(binding["tenant_id"]) or str(row[3] or "") != str(binding["vendor_id"] or ""):
        conn.close(); return JSONResponse({"error": "device identity mismatch"}, status_code=403)
    if str(row[4]) != "ACTIVE":
        conn.close(); return JSONResponse({"error": "device not active"}, status_code=403)
    challenge_id, raw, expires = issue_challenge(conn, device_id.strip(), binding["driver_id"], binding["tenant_id"], binding["vendor_id"])
    audit(conn, user, "DEVICE_CHALLENGE_ISSUED", device_id, f"challenge_id={challenge_id}")
    conn.commit(); conn.close()
    return JSONResponse({"challenge_id": challenge_id, "challenge": raw, "expires_at": expires})


@router.post("/challenge/verify")
async def verify_challenge(request: Request):
    user = current_user(request)
    if not user or (user.get("role") or "").strip().lower() != "driver":
        return JSONResponse({"error": "driver session required"}, status_code=403)
    data = await request.json()
    challenge_id = str(data.get("challenge_id") or "")
    challenge_raw = str(data.get("challenge") or "")
    device_id = str(data.get("device_id") or "")
    device_key_id = str(data.get("device_key_id") or "")
    signature = str(data.get("signature") or "")
    if not all((challenge_id, challenge_raw, device_id, device_key_id, signature)):
        return JSONResponse({"error": "challenge fields required"}, status_code=400)
    conn = get_connection(); cur = conn.cursor()
    binding = _driver_binding(cur, user)
    cur.execute("SELECT * FROM trusted_device_challenges WHERE challenge_id=:1", (challenge_id,))
    row = cur.fetchone()
    if not binding or not row:
        conn.close(); return JSONResponse({"error": "challenge rejected"}, status_code=403)
    cols = [d[0].lower() for d in cur.description]; challenge_row = dict(zip(cols, row))
    if challenge_row["status"] != "ISSUED" or challenge_row["expires_at"] <= __import__("datetime").datetime.now():
        conn.close(); return JSONResponse({"error": "challenge expired or used"}, status_code=403)
    import hashlib
    if hashlib.sha256(challenge_raw.encode()).hexdigest() != challenge_row["challenge_hash"]:
        conn.close(); return JSONResponse({"error": "challenge invalid"}, status_code=403)
    payload = f"{challenge_id}|{device_id}|{challenge_row['issued_at']}|{challenge_raw}"
    state = validate_device(cur, device_id, binding["driver_id"], binding["tenant_id"], binding["vendor_id"], device_key_id, payload, signature)
    if state != "OFFLINE_AUTHORIZED":
        conn.close(); return JSONResponse({"authorized": False, "state": state}, status_code=403)
    cur.execute("UPDATE trusted_device_challenges SET status='USED', used_at=SYSTIMESTAMP WHERE challenge_id=:1 AND status='ISSUED'",
                (challenge_id,))
    audit(conn, user, "DEVICE_CHALLENGE_VERIFIED", device_id, f"challenge_id={challenge_id}")
    conn.commit(); conn.close()
    return JSONResponse({"authorized": True, "state": state, "replay_protected": True})


@router.post("/{device_id}/revoke")
def revoke(request: Request, device_id: str):
    user = current_user(request)
    if not _admin(user):
        return JSONResponse({"error": "not authorized"}, status_code=403)
    conn = get_connection()
    if not revoke_device(conn, device_id, user.get("user_id")):
        conn.close(); return JSONResponse({"error": "device not found or already inactive"}, status_code=404)
    audit(conn, user, "DEVICE_REVOKED", device_id, "")
    conn.commit(); conn.close()
    return JSONResponse({"ok": True, "status": "REVOKED"})
