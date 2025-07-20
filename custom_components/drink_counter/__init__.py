"""Drink Counter integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import service

from .const import DOMAIN, SERVICE_ADD_DRINK, SERVICE_RESET_COUNTERS, ATTR_USER, ATTR_DRINK

PLATFORMS: list[str] = ["sensor", "button"]

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up via YAML is not supported."""
    hass.data.setdefault(DOMAIN, {})

    async def add_drink_service(call):
        user = call.data[ATTR_USER]
        drink = call.data[ATTR_DRINK]
        for entry_id, data in hass.data[DOMAIN].items():
            if data["entry"].data.get("user") == user:
                counts = data.setdefault("counts", {})
                counts[drink] = counts.get(drink, 0) + 1
                for sensor in data.get("sensors", []):
                    await sensor.async_update_state()
                break

    async def reset_counters_service(call):
        user = call.data.get(ATTR_USER)
        for entry_id, data in hass.data[DOMAIN].items():
            if user is None or data["entry"].data.get("user") == user:
                data["counts"] = {drink: 0 for drink in data["entry"].data.get("drinks", {})}
                for sensor in data.get("sensors", []):
                    await sensor.async_update_state()

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_DRINK,
        add_drink_service,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_COUNTERS,
        reset_counters_service,
    )

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    hass.data[DOMAIN].setdefault(entry.entry_id, {"entry": entry, "counts": {}})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
