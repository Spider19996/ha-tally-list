"""Buttons for Tally List."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    SERVICE_RESET_COUNTERS,
    CONF_USER,
    PRICE_LIST_USER,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    if entry.data[CONF_USER] != PRICE_LIST_USER:
        async_add_entities([ResetButton(hass, entry)])


class ResetButton(ButtonEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        user = entry.data[CONF_USER]
        self._attr_name = f"{user} Reset"
        self._attr_unique_id = f"{entry.entry_id}_reset_tally"
        self.entity_id = f"button.{slugify(user)}_reset_tally"

    async def async_press(self) -> None:
        await self._hass.services.async_call(
            DOMAIN,
            SERVICE_RESET_COUNTERS,
            {"user": self._entry.data[CONF_USER]},
            blocking=True,
        )
