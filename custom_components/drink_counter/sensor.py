"""Sensors for Drink Counter."""

from __future__ import annotations

from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_USER


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    user = entry.data[CONF_USER]
    drinks = hass.data[DOMAIN].get("drinks", {})
    sensors = []
    for drink_name, price in drinks.items():
        sensors.append(DrinkCounterSensor(hass, entry, drink_name, price))
    sensors.append(TotalAmountSensor(hass, entry))
    async_add_entities(sensors)
    data.setdefault("sensors", []).extend(sensors)


class DrinkCounterSensor(Entity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, drink: str, price: float) -> None:
        self._hass = hass
        self._entry = entry
        self._drink = drink
        self._price = price
        self._attr_name = f"{entry.data[CONF_USER]} {drink} Count"
        self._attr_unique_id = f"{entry.entry_id}_{drink}_count"
        self._attr_native_value = 0

    async def async_update_state(self):
        self.async_write_ha_state()

    @property
    def native_value(self):
        counts = self._hass.data[DOMAIN][self._entry.entry_id].setdefault("counts", {})
        return counts.get(self._drink, 0)


class TotalAmountSensor(Entity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._attr_name = f"{entry.data[CONF_USER]} Amount Due"
        self._attr_unique_id = f"{entry.entry_id}_amount_due"
        self._attr_unit_of_measurement = "EUR"
        self._attr_native_value = 0

    async def async_update_state(self):
        self.async_write_ha_state()

    @property
    def native_value(self):
        data = self._hass.data[DOMAIN][self._entry.entry_id]
        counts = data.setdefault("counts", {})
        total = 0.0
        drinks = self._hass.data[DOMAIN].get("drinks", {})
        for drink, price in drinks.items():
            total += counts.get(drink, 0) * price
        return round(total, 2)
