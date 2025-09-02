"""Utility helpers for Tally List."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant
else:  # pragma: no cover - used only for type hints
    HomeAssistant = Any


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
