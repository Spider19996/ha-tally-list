"""Tally List integration."""

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
    CONF_USER,
    CONF_FREE_AMOUNT,
    CONF_EXCLUDED_USERS,
    PRICE_LIST_USER,
)

PLATFORMS: list[str] = ["sensor", "button"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up via YAML is not supported."""
    hass.data.setdefault(DOMAIN, {"drinks": {}, "excluded_users": []})

    async def adjust_count_service(call):
        user = call.data[ATTR_USER]
        drink = call.data[ATTR_DRINK]
        count = max(0, call.data.get("count", 0))
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict) or "entry" not in data:
                continue
            if data["entry"].data.get("user") == user:
                counts = data.setdefault("counts", {})
                counts[drink] = count
                for sensor in data.get("sensors", []):
                    await sensor.async_update_state()
                break

    async def add_drink_service(call):
        user = call.data[ATTR_USER]
        drink = call.data[ATTR_DRINK]
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict) or "entry" not in data:
                continue
            if data["entry"].data.get("user") == user:
                counts = data.setdefault("counts", {})
                new_count = counts.get(drink, 0) + 1
                counts[drink] = new_count
                for sensor in data.get("sensors", []):
                    await sensor.async_update_state()
                break

    async def remove_drink_service(call):
        user = call.data[ATTR_USER]
        drink = call.data[ATTR_DRINK]
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict) or "entry" not in data:
                continue
            if data["entry"].data.get("user") == user:
                counts = data.setdefault("counts", {})
                new_count = counts.get(drink, 0) - 1
                if new_count < 0:
                    new_count = 0
                counts[drink] = new_count
                for sensor in data.get("sensors", []):
                    await sensor.async_update_state()
                break

    async def reset_counters_service(call):
        user = call.data.get(ATTR_USER)
        drinks = hass.data[DOMAIN].get("drinks", {})
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict) or "entry" not in data:
                continue
            if user is None or data["entry"].data.get("user") == user:
                data["counts"] = {drink: 0 for drink in drinks}
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
    if not hass.data[DOMAIN].get("drinks") and entry.data.get("drinks"):
        hass.data[DOMAIN]["drinks"] = entry.data["drinks"]
    if hass.data[DOMAIN].get("drinks") and not entry.data.get("drinks"):
        entry_data = {
            "user": entry.data.get("user"),
            "drinks": hass.data[DOMAIN]["drinks"],
            CONF_FREE_AMOUNT: hass.data[DOMAIN].get("free_amount", 0.0),
            CONF_EXCLUDED_USERS: hass.data[DOMAIN].get("excluded_users", []),
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
            "user": entry.data.get("user"),
            "drinks": hass.data[DOMAIN]["drinks"],
            CONF_FREE_AMOUNT: hass.data[DOMAIN]["free_amount"],
            CONF_EXCLUDED_USERS: hass.data[DOMAIN].get("excluded_users", []),
        }
        hass.config_entries.async_update_entry(entry, data=entry_data)
    if (
        not hass.data[DOMAIN].get("excluded_users")
        and entry.data.get(CONF_EXCLUDED_USERS) is not None
    ):
        hass.data[DOMAIN]["excluded_users"] = entry.data[CONF_EXCLUDED_USERS]
    if (
        hass.data[DOMAIN].get("excluded_users") is not None
        and CONF_EXCLUDED_USERS not in entry.data
    ):
        entry_data = {
            "user": entry.data.get("user"),
            "drinks": hass.data[DOMAIN]["drinks"],
            CONF_FREE_AMOUNT: hass.data[DOMAIN].get("free_amount", 0.0),
            CONF_EXCLUDED_USERS: hass.data[DOMAIN]["excluded_users"],
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
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if entry.data.get(CONF_USER) == PRICE_LIST_USER:
            hass.data[DOMAIN].pop("drinks", None)
            hass.data[DOMAIN].pop("free_amount", None)
            hass.data[DOMAIN].pop(CONF_EXCLUDED_USERS, None)
        if not any(
            isinstance(value, dict) and "entry" in value
            for value in hass.data.get(DOMAIN, {}).values()
        ):
            hass.data.pop(DOMAIN, None)
    return unloaded
