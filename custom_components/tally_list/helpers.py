from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, CONF_USER, PRICE_LIST_USER


def device_info_for_entry(hass: HomeAssistant, entry: ConfigEntry) -> DeviceInfo:
    """Return DeviceInfo for a config entry using the price list as parent."""
    device: DeviceInfo = {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": entry.title or entry.data.get(CONF_USER),
    }
    if entry.data.get(CONF_USER) != PRICE_LIST_USER:
        price_entry = next(
            (
                e
                for e in hass.config_entries.async_entries(DOMAIN)
                if e.data.get(CONF_USER) == PRICE_LIST_USER
            ),
            None,
        )
        if price_entry is not None:
            device["via_device"] = (DOMAIN, price_entry.entry_id)
    return device
