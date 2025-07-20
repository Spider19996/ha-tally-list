"""Drink Counter integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN,
    SERVICE_ADD_DRINK,
    SERVICE_REMOVE_DRINK,
    SERVICE_ADJUST_COUNT,
    SERVICE_RESET_COUNTERS,
    ATTR_USER,
    ATTR_DRINK,
    CONF_FREE_AMOUNT,
    CONF_USERS,
    PRICE_LIST_USER,
)

PLATFORMS: list[str] = ["sensor", "button"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up via YAML is not supported."""
    hass.data.setdefault(DOMAIN, {"drinks": {}})

    async def adjust_count_service(call):
        user = call.data[ATTR_USER]
        drink = call.data[ATTR_DRINK]
        count = max(0, call.data.get("count", 0))
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict) or "entry" not in data:
                continue
            counts = data.setdefault("counts", {})
            if user not in counts:
                counts[user] = {}
            counts[user][drink] = count
            for sensor in data.get("sensors", []):
                await sensor.async_update_state()
            break

    async def add_drink_service(call):
        user = call.data[ATTR_USER]
        drink = call.data[ATTR_DRINK]
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict) or "entry" not in data:
                continue
            counts = data.setdefault("counts", {})
            user_counts = counts.setdefault(user, {})
            new_count = user_counts.get(drink, 0) + 1
            user_counts[drink] = new_count
            for sensor in data.get("sensors", []):
                await sensor.async_update_state()
            break

    async def remove_drink_service(call):
        user = call.data[ATTR_USER]
        drink = call.data[ATTR_DRINK]
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict) or "entry" not in data:
                continue
            counts = data.setdefault("counts", {})
            user_counts = counts.setdefault(user, {})
            new_count = user_counts.get(drink, 0) - 1
            if new_count < 0:
                new_count = 0
            user_counts[drink] = new_count
            for sensor in data.get("sensors", []):
                await sensor.async_update_state()
            break

    async def reset_counters_service(call):
        user = call.data.get(ATTR_USER)
        drinks = hass.data[DOMAIN].get("drinks", {})
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict) or "entry" not in data:
                continue
            counts = data.setdefault("counts", {})
            if user is None:
                for usr in list(counts.keys()):
                    counts[usr] = {drink: 0 for drink in drinks}
            else:
                counts.setdefault(user, {})
                counts[user] = {drink: 0 for drink in drinks}
            for sensor in data.get("sensors", []):
                await sensor.async_update_state()

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_DRINK,
        add_drink_service,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_DRINK,
        remove_drink_service,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADJUST_COUNT,
        adjust_count_service,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_RESET_COUNTERS,
        reset_counters_service,
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    hass.data[DOMAIN].setdefault(
        entry.entry_id,
        {"entry": entry, "counts": {}},
    )
    counts = hass.data[DOMAIN][entry.entry_id].setdefault("counts", {})
    for user in entry.data.get(CONF_USERS, []):
        counts.setdefault(user, {})
    if not hass.data[DOMAIN].get("drinks") and entry.data.get(CONF_DRINKS):
        hass.data[DOMAIN]["drinks"] = entry.data[CONF_DRINKS]
    if hass.data[DOMAIN].get("drinks") and not entry.data.get(CONF_DRINKS):
        entry_data = {
            CONF_USERS: entry.data.get(CONF_USERS, []),
            CONF_DRINKS: hass.data[DOMAIN]["drinks"],
            CONF_FREE_AMOUNT: hass.data[DOMAIN].get("free_amount", 0.0),
        }
        hass.config_entries.async_update_entry(entry, data=entry_data)
    if (
        not hass.data[DOMAIN].get("free_amount")
        and entry.data.get(CONF_FREE_AMOUNT) is not None
    ):
        hass.data[DOMAIN]["free_amount"] = entry.data[CONF_FREE_AMOUNT]
    if (
        hass.data[DOMAIN].get("free_amount") is not None
        and CONF_FREE_AMOUNT not in entry.data
    ):
        entry_data = {
            CONF_USERS: entry.data.get(CONF_USERS, []),
            CONF_DRINKS: hass.data[DOMAIN]["drinks"],
            CONF_FREE_AMOUNT: hass.data[DOMAIN]["free_amount"],
        }
        hass.config_entries.async_update_entry(entry, data=entry_data)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
