from __future__ import annotations

import hashlib
import hmac
import os

PBKDF2_ITERATIONS = 100_000


def hash_pin(pin: str) -> str:
    """Hash a PIN using PBKDF2 with a random salt.

    The returned value is formatted as ``<salt>$<hash>`` where both parts are
    hex encoded.
    """
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PBKDF2_ITERATIONS)
    return f"{salt.hex()}${key.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    """Verify a PIN against a stored hash."""
    if "$" not in stored:
        return False
    salt_hex, hashed = stored.split("$", 1)
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    key = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(key.hex(), hashed)
