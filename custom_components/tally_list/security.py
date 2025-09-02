from __future__ import annotations

import hashlib
import hmac
import os

PBKDF2_ALGORITHM = "pbkdf2_sha256"
PBKDF2_ITERATIONS = 100_000


def hash_pin(pin: str) -> str:
    """Hash a PIN using PBKDF2 with a random salt.

    The returned value is formatted as
    ``pbkdf2_sha256$<iterations>$<salt>$<hash>`` where all parts are hex encoded.
    """
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_ALGORITHM}${PBKDF2_ITERATIONS}${salt.hex()}${key.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    """Verify a PIN against a stored hash.

    The stored value must be formatted as
    ``pbkdf2_sha256$<iterations>$<salt>$<hash>`` where all parts are hex
    encoded.
    """
    parts = stored.split("$")

    if len(parts) != 4:
        return False

    algorithm, iterations_hex, salt_hex, hashed = parts

    if algorithm != PBKDF2_ALGORITHM:
        return False

    try:
        iterations = int(iterations_hex)
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False

    key = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, iterations)
    return hmac.compare_digest(key.hex(), hashed)
