"""Trusted Driver device and finite offline-authorization primitives."""

import base64
import hashlib
import logging
import uuid
from datetime import datetime, timedelta

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization

log = logging.getLogger("rentago.trusted_devices")


def _decode(value):
    return base64.urlsafe_b64decode(str(value).encode("ascii") + b"=" * (-len(str(value)) % 4))


def verify_public_key(public_key_b64, algorithm="ED25519"):
    raw = _decode(public_key_b64)
    if algorithm == "ED25519" and len(raw) != 32:
        raise ValueError("Ed25519 public key must be 32 bytes")
    if algorithm == "ED25519":
        Ed25519PublicKey.from_public_bytes(raw)
    elif algorithm == "ECDSA_P256_SHA256":
        key = serialization.load_der_public_key(raw)
        if not isinstance(key, ec.EllipticCurvePublicKey) or key.curve.name != "secp256r1":
            raise ValueError("P-256 public key required")
    else:
        raise ValueError("unsupported trusted-device algorithm")
    return raw


def verify_signature(public_key_b64, payload, signature_b64, algorithm="ED25519"):
    try:
        public_raw = verify_public_key(public_key_b64, algorithm)
        signature_raw = _decode(signature_b64)
        payload_raw = str(payload).encode("utf-8")
        if algorithm == "ED25519":
            Ed25519PublicKey.from_public_bytes(public_raw).verify(signature_raw, payload_raw)
        else:
            key = serialization.load_der_public_key(public_raw)
            key.verify(signature_raw, payload_raw, ec.ECDSA(hashes.SHA256()))
        log.info("trusted signature verify=PASS public_fp=%s payload_fp=%s signature_len=%s",
                 hashlib.sha256(public_raw).hexdigest(),
                 hashlib.sha256(payload_raw).hexdigest(), len(signature_raw))
        return True
    except (ValueError, InvalidSignature, TypeError, UnicodeError):
        try:
            log.warning("trusted signature verify=FAIL public_fp=%s payload_fp=%s signature_len=%s",
            hashlib.sha256(verify_public_key(public_key_b64, algorithm)).hexdigest(),
                        hashlib.sha256(str(payload).encode("utf-8")).hexdigest(),
                        len(_decode(signature_b64)))
        except Exception:
            log.warning("trusted signature verify=FAIL diagnostics-unavailable")
        return False


def device_state(row, now=None):
    """Return a stable authorization state from a trusted-device row."""
    if not row:
        return "DEVICE_NOT_PROVISIONED"
    now = now or datetime.now()
    status = str(row.get("status") or "").upper()
    if status in {"REVOKED", "SUSPENDED"}:
        return "DEVICE_REVOKED" if status == "REVOKED" else "DEVICE_SUSPENDED"
    expires = row.get("offline_authorized_until")
    if expires and now >= expires:
        return "OFFLINE_EXPIRED"
    return "OFFLINE_AUTHORIZED"


def provision_device(conn, device_id, driver_id, tenant_id, vendor_id, device_key_id,
                     public_key_b64, provisioned_by, offline_days=7,
                     device_name="", platform="Android", algorithm="ED25519"):
    verify_public_key(public_key_b64, algorithm)
    log.info("trusted provision device=%s algorithm=%s public_fp=%s", device_id, algorithm,
             hashlib.sha256(verify_public_key(public_key_b64, algorithm)).hexdigest())
    if offline_days < 1 or offline_days > 30:
        raise ValueError("offline authorization must be 1-30 days")
    cur = conn.cursor()
    cur.execute("SELECT status FROM trusted_driver_devices WHERE device_id=:1", (device_id,))
    if cur.fetchone():
        raise ValueError("device already provisioned; revoke before reprovisioning")
    cur.execute(
        "INSERT INTO trusted_driver_devices (device_id,driver_id,tenant_id,vendor_id,device_key_id,"
        "public_key,algorithm,device_name,platform,provisioned_by,offline_authorized_until,status) "
        "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9,:10,:11,'ACTIVE')",
        (device_id, driver_id, tenant_id, vendor_id, device_key_id, public_key_b64,
         algorithm, device_name[:200], platform[:30], provisioned_by,
         datetime.now() + timedelta(days=offline_days)),
    )


def validate_device(cur, device_id, driver_id, tenant_id, vendor_id,
                    device_key_id=None,
                    payload=None, signature_b64=None):
    cur.execute("SELECT * FROM trusted_driver_devices WHERE device_id=:1", (device_id,))
    row = cur.fetchone()
    if not row:
        return "DEVICE_NOT_PROVISIONED"
    data = dict(zip([d[0].lower() for d in cur.description], row))
    if str(data.get("driver_id")) != str(driver_id) or str(data.get("tenant_id")) != str(tenant_id):
        return "DEVICE_IDENTITY_MISMATCH"
    if device_key_id is not None and str(data.get("device_key_id")) != str(device_key_id):
        return "DEVICE_KEY_MISMATCH"
    if vendor_id is not None and str(data.get("vendor_id") or "") != str(vendor_id):
        return "VENDOR_MISMATCH"
    state = device_state(data)
    if state != "OFFLINE_AUTHORIZED":
        return state
    if payload is not None and not signature_b64:
        return "SIGNATURE_REQUIRED"
    algorithm = str(data.get("algorithm") or "ED25519").upper()
    if payload is not None and not verify_signature(data["public_key"], payload, signature_b64, algorithm):
        return "SIGNATURE_INVALID"
    cur.execute("UPDATE trusted_driver_devices SET last_online_validation_at=SYSTIMESTAMP, updated_at=SYSTIMESTAMP WHERE device_id=:1",
                (device_id,))
    return "OFFLINE_AUTHORIZED"


def revoke_device(conn, device_id, revoked_by, status="REVOKED"):
    cur = conn.cursor()
    cur.execute("UPDATE trusted_driver_devices SET status=:1, revoked_at=SYSTIMESTAMP, revoked_by=:2, updated_at=SYSTIMESTAMP WHERE device_id=:3 AND status='ACTIVE'",
                (status, revoked_by, device_id))
    return bool(cur.rowcount)


def issue_challenge(conn, device_id, driver_id, tenant_id, vendor_id):
    raw, challenge_hash = _token()
    challenge_id = "CH-" + uuid.uuid4().hex
    expires = datetime.now() + timedelta(minutes=5)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO trusted_device_challenges (challenge_id,device_id,driver_id,tenant_id,"
        "vendor_id,challenge_hash,expires_at) VALUES (:1,:2,:3,:4,:5,:6,:7)",
        (challenge_id, device_id, driver_id, tenant_id, vendor_id, challenge_hash, expires),
    )
    return challenge_id, raw, expires


def issue_offline_authorization(conn, device, issued_by, days=7):
    if days < 1 or days > 30:
        raise ValueError("offline authorization must be 1-30 days")
    now = datetime.now()
    device_expiry = device.get("offline_authorized_until")
    expires = min(device_expiry, now + timedelta(days=days)) if device_expiry else now + timedelta(days=days)
    auth_id = "OFF-" + uuid.uuid4().hex
    epoch = uuid.uuid4().hex
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO trusted_offline_authorizations (offline_authorization_id,device_id,device_key_id,"
        "driver_id,tenant_id,vendor_id,authorization_epoch,expires_at,issued_by) "
        "VALUES (:1,:2,:3,:4,:5,:6,:7,:8,:9)",
        (auth_id, device["device_id"], device["device_key_id"], device["driver_id"],
         device["tenant_id"], device.get("vendor_id"), epoch, expires, issued_by),
    )
    return auth_id, epoch, expires


def _token():
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()
