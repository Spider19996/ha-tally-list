"""Utility helpers for Tally List."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

try:
    from homeassistant.util import slugify
except Exception:  # pragma: no cover - Home Assistant not available
    import re
    import unicodedata

    def slugify(value: str) -> str:
        """Simplified fallback slugify implementation."""
        normalized = (
            unicodedata.normalize("NFKD", value)
            .encode("ascii", "ignore")
            .decode("ascii")
        )
        return re.sub(r"[^a-z0-9_]+", "_", normalized.lower()).strip("_")

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
else:  # pragma: no cover - used only for type hints
    HomeAssistant = Any

try:
    from .const import DOMAIN, CONF_CASH_USER_NAME, CASH_USER_SLUG
except Exception:  # pragma: no cover - direct import for tests
    from const import DOMAIN, CONF_CASH_USER_NAME, CASH_USER_SLUG


def get_person_name(hass: HomeAssistant, user_id: str | None) -> str | None:
    """Return the person name for a Home Assistant user ID.

    Parameters:
        hass: HomeAssistant instance used to access state data.
        user_id: The Home Assistant user ID to look up.

    Returns:
        The name of the person entity linked to the user ID, or ``None`` if no
        matching person is found or ``user_id`` is ``None``.
    """
    if user_id is None:
        return None

    for state in hass.states.async_all("person"):
        if state.attributes.get("user_id") == user_id:
            return state.name
    return None


def get_user_slug(hass: HomeAssistant, username: str) -> str:
    """Return the slug for a user name.

    Applies Home Assistant's ``slugify`` and handles the special cash user.
    """
    cash_name = hass.data.get(DOMAIN, {}).get(CONF_CASH_USER_NAME, "")
    if username.strip().lower() == cash_name.strip().lower():
        return CASH_USER_SLUG
    return slugify(username)
