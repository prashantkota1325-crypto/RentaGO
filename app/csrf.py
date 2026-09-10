"""Double-submit CSRF token helpers for cookie-authenticated forms."""

import hmac
import secrets

COOKIE_NAME = "rentago_csrf"
FIELD_NAME = "csrf_token"


def new_token():
    return secrets.token_urlsafe(32)


def valid(expected, supplied):
    return bool(expected and supplied and hmac.compare_digest(str(expected), str(supplied)))
