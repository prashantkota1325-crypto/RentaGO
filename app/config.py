"""
RentaGO Web - Configuration.

Connection settings are read from environment variables (or a local .env) so
secrets are not hard-coded. Defaults target a local Oracle XE 21c install
(service name XEPDB1, pluggable database).
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv():
    """Load BASE_DIR/.env into the process env (if not already set).

    Uses python-dotenv when installed; otherwise a tiny built-in parser so the
    app still picks up the file without the extra dependency.
    """
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    try:
        from dotenv import load_dotenv  # type: ignore

        load_dotenv(env_file)
        return
    except Exception:
        pass
    try:
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


_load_dotenv()

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


_cookie_domain = _env("RENTAGO_SESSION_COOKIE_DOMAIN", "").strip()


class Settings:
    # --- Oracle connection ---
    DB_HOST: str = _env("RENTAGO_DB_HOST", "localhost")
    DB_PORT: str = _env("RENTAGO_DB_PORT", "1521")
    DB_SERVICE: str = _env("RENTAGO_DB_SERVICE", "XEPDB1")
    DB_USER: str = _env("RENTAGO_DB_USER", "RENTAGO")
    DB_PASSWORD: str = _env("RENTAGO_DB_PASSWORD", "")

    # --- App ---
    APP_NAME: str = "RentaGO Prototype Web"
    ENVIRONMENT: str = _env("RENTAGO_ENVIRONMENT", "development").strip().lower()
    SECRET_KEY: str = _env("RENTAGO_SECRET", "")
    SESSION_TTL_MINUTES: int = int(_env("RENTAGO_SESSION_TTL", "120"))
    INTERNAL_IDLE_TIMEOUT_MINUTES: int = int(_env("RENTAGO_INTERNAL_IDLE_TIMEOUT", "5"))
    # Allow session cookie to work across subdomains/tunnel (trycloudflare, LAN, localhost)
    # Set to None to restrict to exact origin only; set to a domain like ".rentago.local" 
    # or "." to allow across all subdomains of that base.
    SESSION_COOKIE_DOMAIN: str | None = (
        None if _cookie_domain.lower() in ("", "none", "null") else _cookie_domain
    )
    SESSION_COOKIE_SECURE: bool = _env(
        "RENTAGO_SESSION_COOKIE_SECURE",
        "true" if ENVIRONMENT == "production" else "false",
    ).strip().lower() in ("1", "true", "yes", "on")
    GOOGLE_MAPS_API_KEY: str = _env("RENTAGO_GOOGLE_MAPS_API_KEY", "").strip()
    MAP_PROVIDER: str = _env("RENTAGO_MAP_PROVIDER", "google").strip().lower()
    MAPPLS_API_KEY: str = _env("RENTAGO_MAPPLS_API_KEY", "").strip()
    SMTP_HOST: str = _env("RENTAGO_SMTP_HOST", "smtpout.secureserver.net").strip()
    SMTP_PORT: int = int(_env("RENTAGO_SMTP_PORT", "465"))
    SMTP_SECURITY: str = _env("RENTAGO_SMTP_SECURITY", "ssl").strip().lower()
    SMTP_USER: str = _env("RENTAGO_SMTP_USER", "").strip()
    SMTP_PASSWORD: str = _env("RENTAGO_SMTP_PASSWORD", "")
    SMTP_FROM_NAME: str = _env("RENTAGO_SMTP_FROM_NAME", "RentaGO Technologies Pvt. Ltd.").strip()

    # --- Source workbook (used by the import tool) ---
    WORKBOOK_PATH: str = _env(
        "RENTAGO_WORKBOOK",
        r"C:\Users\Prashant Kota\RentaGO_Prototype_new.xlsm",
    )

    @property
    def dsn(self) -> str:
        return f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_SERVICE}"

    @property
    def admin_dsn(self) -> str:
        # Connect to the container database / admin account to bootstrap
        return f"{self.DB_HOST}:{self.DB_PORT}/XEPDB1"


settings = Settings()


def validate_settings() -> None:
    """Reject unsafe production defaults before accepting requests."""
    if settings.ENVIRONMENT != "production":
        return
    if len(settings.SECRET_KEY) < 32 or settings.SECRET_KEY in {"change-me", ""}:
        raise RuntimeError("RENTAGO_SECRET must be a strong production secret")
    if not settings.DB_PASSWORD:
        raise RuntimeError("RENTAGO_DB_PASSWORD must be configured in production")
    if not settings.SESSION_COOKIE_SECURE:
        raise RuntimeError("RENTAGO_SESSION_COOKIE_SECURE must be enabled in production")
