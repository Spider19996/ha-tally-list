"""Sensors for Tally List."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .const import DOMAIN, CONF_USER, PRICE_LIST_USERS, CONF_CURRENCY


def _local_suffix(hass: HomeAssistant, en: str, de: str) -> str:
    """Return language-specific sensor name suffix."""
    language = (hass.config.language or "").lower()
    return de if language.startswith("de") else en


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    data = hass.data[DOMAIN][entry.entry_id]
    user = entry.data[CONF_USER]
    drinks = hass.data[DOMAIN].get("drinks", {})
    sensors: list[SensorEntity] = []

    if user in PRICE_LIST_USERS:
        for drink_name, price in drinks.items():
            sensors.append(DrinkPriceSensor(hass, entry, drink_name, price))
        sensors.append(FreeAmountSensor(hass, entry))
    else:
        for drink_name, price in drinks.items():
            sensors.append(TallyListSensor(hass, entry, drink_name, price))
        sensors.append(TotalAmountSensor(hass, entry))

    data.setdefault("sensors", []).extend(sensors)
    async_add_entities(sensors)


class TallyListSensor(RestoreEntity, SensorEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        drink: str,
        price: float,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._drink = drink
        self._price = price
        self._attr_should_poll = False
        self._attr_name = (
            f"{entry.data[CONF_USER]} {drink} "
            f"{_local_suffix(hass, 'Count', 'Anzahl')}"
        )
        self._attr_unique_id = f"{entry.entry_id}_{drink}_count"
        self._attr_native_value = 0
        self._attr_native_unit_of_measurement = None

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
            counts[self._drink] = restored
            self._attr_native_value = restored
        await self.async_update_state()

    async def async_update_state(self):
        self._attr_native_unit_of_measurement = None
        self.async_write_ha_state()

    @property
    def native_value(self):
        counts = self._hass.data[DOMAIN][self._entry.entry_id].setdefault(
            "counts",
            {},
        )
        return counts.get(self._drink, 0)


class DrinkPriceSensor(SensorEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        drink: str,
        price: float,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._drink = drink
        self._price = price
        self._attr_should_poll = False
        self._attr_name = (
            f"{entry.data[CONF_USER]} {drink} "
            f"{_local_suffix(hass, 'Price', 'Preis')}"
        )
        self._attr_unique_id = f"{entry.entry_id}_{drink}_price"
        self.entity_id = f"sensor.price_list_{slugify(drink)}_price"
        self._attr_native_unit_of_measurement = hass.data.get(DOMAIN, {}).get(
            CONF_CURRENCY, "€"
        )
        self._attr_suggested_display_precision = 2

    async def async_added_to_hass(self) -> None:
        await self.async_update_state()

    async def async_update_state(self):
        self._attr_native_unit_of_measurement = self._hass.data.get(
            DOMAIN, {}
        ).get(CONF_CURRENCY, "€")
        self.async_write_ha_state()

    @property
    def native_value(self):
        drinks = self._hass.data.get(DOMAIN, {}).get("drinks", {})
        return round(drinks.get(self._drink, self._price), 2)


class FreeAmountSensor(SensorEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._attr_should_poll = False
        self._attr_name = (
            f"{entry.data[CONF_USER]} "
            f"{_local_suffix(hass, 'Free amount', 'Freibetrag')}"
        )
        self._attr_unique_id = f"{entry.entry_id}_free_amount"
        self.entity_id = "sensor.price_list_free_amount"
        self._attr_native_unit_of_measurement = hass.data.get(DOMAIN, {}).get(
            CONF_CURRENCY, "€"
        )
        self._attr_suggested_display_precision = 2

    async def async_added_to_hass(self) -> None:
        await self.async_update_state()

    async def async_update_state(self):
        self._attr_native_unit_of_measurement = self._hass.data.get(
            DOMAIN, {}
        ).get(CONF_CURRENCY, "€")
        self.async_write_ha_state()

    @property
    def native_value(self):
        return round(self._hass.data.get(DOMAIN, {}).get("free_amount", 0.0), 2)


class TotalAmountSensor(RestoreEntity, SensorEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._attr_should_poll = False
        self._attr_name = (
            f"{entry.data[CONF_USER]} "
            f"{_local_suffix(hass, 'Amount due', 'Offener Betrag')}"
        )
        self._attr_unique_id = f"{entry.entry_id}_amount_due"
        self._attr_native_unit_of_measurement = hass.data.get(DOMAIN, {}).get(
            CONF_CURRENCY, "€"
        )
        self._attr_native_value = 0
        self._attr_suggested_display_precision = 2

    async def async_added_to_hass(self) -> None:
        await self.async_update_state()

    async def async_update_state(self):
        self._attr_native_unit_of_measurement = self._hass.data.get(
            DOMAIN, {}
        ).get(CONF_CURRENCY, "€")
        self.async_write_ha_state()

    @property
    def native_value(self):
        data = self._hass.data[DOMAIN][self._entry.entry_id]
        counts = data.setdefault("counts", {})
        total = 0.0
        drinks = self._hass.data[DOMAIN].get("drinks", {})
        for drink, price in drinks.items():
            total += counts.get(drink, 0) * price
        free_amount = self._hass.data.get(DOMAIN, {}).get("free_amount", 0.0)
        total -= free_amount
        if total < 0:
            total = 0.0
        return round(total, 2)
