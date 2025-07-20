"""Sensors for Drink Counter."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, CONF_USERS, CONF_USER, PRICE_LIST_USER


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    data = hass.data[DOMAIN][entry.entry_id]
    users = entry.data.get(CONF_USERS, [])
    drinks = hass.data[DOMAIN].get("drinks", {})
    sensors: list[SensorEntity] = []

    for user in users:
        if user == PRICE_LIST_USER:
            for drink_name, price in drinks.items():
                sensors.append(
                    DrinkPriceSensor(hass, entry, user, drink_name, price)
                )
            sensors.append(FreeAmountSensor(hass, entry, user))
        else:
            for drink_name, price in drinks.items():
                sensors.append(
                    DrinkCounterSensor(hass, entry, user, drink_name, price)
                )
            sensors.append(TotalAmountSensor(hass, entry, user))

    data.setdefault("sensors", []).extend(sensors)
    async_add_entities(sensors)


class DrinkCounterSensor(RestoreEntity, SensorEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        user: str,
        drink: str,
        price: float,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._user = user
        self._drink = drink
        self._price = price
        self._attr_should_poll = False
        self._attr_name = f"{user} {drink} Count"
        self._attr_unique_id = f"{entry.entry_id}_{user}_{drink}_count"
        self._attr_native_value = 0

    async def async_added_to_hass(self) -> None:
        last_state = await self.async_get_last_state()
        if (
            last_state is not None
            and last_state.state not in (None, "unknown", "unavailable")
        ):
            try:
                restored = int(float(last_state.state))
            except ValueError:
                restored = 0
            counts = self._hass.data[DOMAIN][self._entry.entry_id].setdefault(
                "counts",
                {},
            )
            user_counts = counts.setdefault(self._user, {})
            user_counts[self._drink] = restored
            self._attr_native_value = restored
        await self.async_update_state()

    async def async_update_state(self):
        self.async_write_ha_state()

    @property
    def native_value(self):
        counts = self._hass.data[DOMAIN][self._entry.entry_id].setdefault(
            "counts",
            {},
        )
        user_counts = counts.setdefault(self._user, {})
        return user_counts.get(self._drink, 0)


class DrinkPriceSensor(SensorEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        user: str,
        drink: str,
        price: float,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._user = user
        self._drink = drink
        self._price = price
        self._attr_should_poll = False
        self._attr_name = f"{user} {drink} Price"
        self._attr_unique_id = f"{entry.entry_id}_{user}_{drink}_price"
        self._attr_unit_of_measurement = "EUR"

    async def async_added_to_hass(self) -> None:
        await self.async_update_state()

    async def async_update_state(self):
        self.async_write_ha_state()

    @property
    def native_value(self):
        drinks = self._hass.data.get(DOMAIN, {}).get("drinks", {})
        return drinks.get(self._drink, self._price)


class FreeAmountSensor(SensorEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, user: str) -> None:
        self._hass = hass
        self._entry = entry
        self._user = user
        self._attr_should_poll = False
        self._attr_name = f"{user} Free Amount"
        self._attr_unique_id = f"{entry.entry_id}_{user}_free_amount"
        self._attr_unit_of_measurement = "EUR"

    async def async_added_to_hass(self) -> None:
        await self.async_update_state()

    async def async_update_state(self):
        self.async_write_ha_state()

    @property
    def native_value(self):
        return self._hass.data.get(DOMAIN, {}).get("free_amount", 0.0)


class TotalAmountSensor(RestoreEntity, SensorEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, user: str) -> None:
        self._hass = hass
        self._entry = entry
        self._user = user
        self._attr_should_poll = False
        self._attr_name = f"{user} Amount Due"
        self._attr_unique_id = f"{entry.entry_id}_{user}_amount_due"
        self._attr_unit_of_measurement = "EUR"
        self._attr_native_value = 0

    async def async_added_to_hass(self) -> None:
        await self.async_update_state()

    async def async_update_state(self):
        self.async_write_ha_state()

    @property
    def native_value(self):
        data = self._hass.data[DOMAIN][self._entry.entry_id]
        counts = data.setdefault("counts", {})
        user_counts = counts.setdefault(self._user, {})
        total = 0.0
        drinks = self._hass.data[DOMAIN].get("drinks", {})
        for drink, price in drinks.items():
            total += user_counts.get(drink, 0) * price
        free_amount = self._hass.data.get(DOMAIN, {}).get("free_amount", 0.0)
        total -= free_amount
        if total < 0:
            total = 0.0
        return round(total, 2)
