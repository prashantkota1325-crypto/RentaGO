"""
Security helpers matching the RentaGO VBA password scheme.

VBA stores:  "<saltHex>:<SHA256Hex(saltHex & password)>"
    - salt is a hex string
    - SHA-256 over UTF-8 bytes of (salt + password), hex-encoded, case-insensitive.

This mirrors RentaGO_MacroHelper.bas so users imported from the workbook can
authenticate without resetting passwords.
"""

import hashlib
import os


def sha256_hex(payload: str) -> str:
    """SHA-256 (hex) over the UTF-8 bytes of payload. Matches VBA SHA256Hex."""
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def random_salt_hex(byte_len: int = 16) -> str:
    """Random hex salt, matching the VBA RandomSaltHex (default 32 hex chars)."""
    return os.urandom(byte_len).hex()


def hash_password(password: str, salt_hex: str | None = None) -> str:
    """Return '<saltHex>:<hashHex>' for a given password."""
    salt = salt_hex or random_salt_hex()
    return f"{salt}:{sha256_hex(salt + password)}"


def verify_password(password: str, stored: str | None) -> bool:
    """Check password against a stored '<salt>:<hash>' string OR a plain password vault.
    
    The stored string can be in either of two formats:
    1. '<salt>:<hash>' - the VBA salted hash format (has colon)
    2. Plain password - legacy vault format (no colon; legacy data only)
    
    If the stored string contains a colon, it's treated as format 1.
    Otherwise, it's treated as a plain password to compare directly.
    """
    if not stored:
        return False
    
    if ":" in stored:
        # Format 1: '<salt>:<hash>' - VBA salted hash format
        salt, expected = stored.split(":", 1)
        if not salt or not expected:
            return False
        return sha256_hex(salt + password).lower() == expected.lower()
    else:
        # Format 2: Plain password vault (legacy VBA format, no colon)
        # Direct comparison - the stored value is the expected password
        return password == stored
