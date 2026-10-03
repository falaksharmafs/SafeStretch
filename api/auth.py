import hmac
import os

from fastapi import Header, HTTPException

KEYS = {k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()}
ADMIN_KEY = os.getenv("ADMIN_KEY", "")


def key_ok(given, valid):
    """Constant-time membership test."""
    return bool(given) and any(hmac.compare_digest(given, v) for v in valid if v)


def require_key(x_api_key: str | None = Header(default=None)):
    if not KEYS:                      # dev mode: no keys configured -> open
        return
    if not key_ok(x_api_key, KEYS | {ADMIN_KEY}):
        raise HTTPException(401, "Missing or invalid X-API-Key")


def require_admin(x_api_key: str | None = Header(default=None)):
    if not ADMIN_KEY or not key_ok(x_api_key, {ADMIN_KEY}):
        raise HTTPException(403, "Admin key required")
