"""Buttons for Tally List."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    SERVICE_RESET_COUNTERS,
    CONF_USER,
    CONF_OVERRIDE_USERS,
    PRICE_LIST_USERS,
    CONF_CASH_USER_NAME,
    CASH_USER_SLUG,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    if entry.data[CONF_USER] not in PRICE_LIST_USERS:
        async_add_entities([ResetButton(hass, entry)])


class ResetButton(ButtonEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        user = entry.data[CONF_USER]
        self._attr_name = f"{user} Reset"
        self._attr_unique_id = f"{entry.entry_id}_reset_tally"
        user_slug = slugify(user)
        cash_name = hass.data.get(DOMAIN, {}).get(CONF_CASH_USER_NAME, "")
        if user.strip().lower() == cash_name.strip().lower():
            user_slug = CASH_USER_SLUG
        self.entity_id = f"button.{user_slug}_reset_tally"

    async def async_press(self) -> None:
        user_id = self._context.user_id if self._context else None
        if user_id is not None:
            hass_user = await self._hass.auth.async_get_user(user_id)
            if hass_user is not None:
                override_users = self._hass.data.get(DOMAIN, {}).get(
                    CONF_OVERRIDE_USERS,
                    [],
                )
                person_name = None
                for state in self._hass.states.async_all("person"):
                    if state.attributes.get("user_id") == hass_user.id:
                        person_name = state.name
                        break
                if person_name not in override_users:
                    raise Unauthorized

        await self._hass.services.async_call(
            DOMAIN,
            SERVICE_RESET_COUNTERS,
            {"user": self._entry.data[CONF_USER]},
            blocking=True,
        )
