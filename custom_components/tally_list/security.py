from __future__ import annotations

import hashlib
import hmac
import os

PBKDF2_ITERATIONS = 100_000


def hash_pin(pin: str) -> str:
    """Hash a PIN using PBKDF2 with a random salt.

    The returned value is formatted as ``<iterations>$<salt>$<hash>`` where all
    parts are hex encoded.
    """
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_ITERATIONS}${salt.hex()}${key.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    """Verify a PIN against a stored hash.

    Supports the current ``<iterations>$<salt>$<hash>`` format as well as the
    legacy ``<salt>$<hash>`` format which assumes ``PBKDF2_ITERATIONS``
    iterations.
    """
    if "$" not in stored:
        return False

    parts = stored.split("$")
    if len(parts) == 2:
        salt_hex, hashed = parts
        iterations = PBKDF2_ITERATIONS
    elif len(parts) == 3:
        iterations_hex, salt_hex, hashed = parts
        try:
            iterations = int(iterations_hex)
        except ValueError:
            return False
    else:
        return False

    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False

    key = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, iterations)
    return hmac.compare_digest(key.hex(), hashed)
