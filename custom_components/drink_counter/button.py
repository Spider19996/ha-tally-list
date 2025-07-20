"""Buttons for Drink Counter."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    SERVICE_RESET_COUNTERS,
    CONF_USERS,
    PRICE_LIST_USER,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    buttons = []
    for user in entry.data.get(CONF_USERS, []):
        if user != PRICE_LIST_USER:
            buttons.append(ResetButton(hass, entry, user))
    if buttons:
        async_add_entities(buttons)


class ResetButton(ButtonEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, user: str) -> None:
        self._hass = hass
        self._entry = entry
        self._user = user
        self._attr_name = f"{user} Reset"
        self._attr_unique_id = f"{entry.entry_id}_{user}_reset"

    async def async_press(self) -> None:
        await self._hass.services.async_call(
            DOMAIN,
            SERVICE_RESET_COUNTERS,
            {"user": self._user},
            blocking=True,
        )
