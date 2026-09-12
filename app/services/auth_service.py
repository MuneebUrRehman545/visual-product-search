"""Authentication service providing secure password hashing, token generation, and user validation."""

import base64
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import os
import secrets
from typing import Any, Dict, Optional, Tuple

_INSECURE_DEFAULT_SECRET = "visual-product-search-super-secret-key-2026-week3"
_PLACEHOLDER_SECRETS = {"change-me-in-production", "your_secret_key_here", _INSECURE_DEFAULT_SECRET}


def _resolve_jwt_secret() -> str:
    secret = os.getenv("AUTH_SECRET_KEY")
    app_env = os.getenv("APP_ENV", "development").lower()
    if not secret or secret.strip() in _PLACEHOLDER_SECRETS:
        if app_env == "production":
            raise RuntimeError(
                "CRITICAL SECURITY CONFIGURATION ERROR: AUTH_SECRET_KEY environment variable "
                "must be explicitly set to a strong secret in production mode. "
                "Refusing to start with insecure default secret."
            )
        return _INSECURE_DEFAULT_SECRET
    return secret.strip()


JWT_SECRET = _resolve_jwt_secret()
TOKEN_EXPIRY_DAYS = 7


def generate_salt() -> str:
    """Generate a cryptographically secure 32-character hexadecimal salt."""
    return secrets.token_hex(16)


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256 with 100,000 iterations.
    
    Returns:
        Tuple[str, str]: (password_hash_hex, salt_hex)
    """
    if salt is None:
        salt = generate_salt()
    
    pwd_bytes = password.encode("utf-8")
    salt_bytes = salt.encode("utf-8")
    key = hashlib.pbkdf2_hmac("sha256", pwd_bytes, salt_bytes, iterations=100000)
    return key.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2 hash."""
    computed_hash, _ = hash_password(password, salt)
    return hmac.compare_digest(computed_hash, password_hash)


def create_access_token(user_id: int, email: str, username: str) -> str:
    """Generate a signed URL-safe JWT-like bearer token."""
    exp = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRY_DAYS)
    payload = {
        "user_id": user_id,
        "email": email,
        "username": username,
        "exp": int(exp.timestamp()),
    }
    payload_json = json.dumps(payload, separators=(",", ":"))
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8").rstrip("=")
    
    signature = hmac.new(
        JWT_SECRET.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    
    return f"{payload_b64}.{signature}"


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Validate token signature and return payload dict if unexpired and valid."""
    if not token or "." not in token:
        return None
    
    try:
        payload_b64, signature = token.split(".", 1)
        expected_sig = hmac.new(
            JWT_SECRET.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        
        if not hmac.compare_digest(expected_sig, signature):
            return None
        
        # Pad base64 string
        padded_b64 = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(padded_b64).decode("utf-8")
        payload = json.loads(payload_json)
        
        # Check expiration
        exp = payload.get("exp", 0)
        if datetime.now(timezone.utc).timestamp() > exp:
            return None
        
        return payload
    except Exception:
        return None
