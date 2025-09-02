"""Sensors for Tally List."""

from __future__ import annotations

import csv
import logging
import os
import re
from collections import deque
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .utils import get_user_slug

from .const import (
    DOMAIN,
    CONF_USER,
    PRICE_LIST_USERS,
    CONF_CURRENCY,
    CONF_CASH_USER_NAME,
)

_LOGGER = logging.getLogger(__name__)


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

    cash_name = hass.data.get(DOMAIN, {}).get(CONF_CASH_USER_NAME, "")
    if (
        user.strip().lower() == cash_name.strip().lower()
        and "feed_add_entities" not in hass.data[DOMAIN]
    ):
        hass.data[DOMAIN]["feed_add_entities"] = async_add_entities
        hass.data[DOMAIN]["feed_entry_id"] = entry.entry_id
        feed_sensors: dict[int, FreeDrinkFeedSensor] = {}
        base_dir = hass.config.path("backup", "tally_list", "free_drinks")
        if os.path.isdir(base_dir):
            for name in os.listdir(base_dir):
                match = re.match(r"free_drinks_(\d{4})\.csv$", name)
                if not match:
                    continue
                year = int(match.group(1))
                feed_sensors[year] = FreeDrinkFeedSensor(hass, entry, year)
        if feed_sensors:
            async_add_entities(list(feed_sensors.values()))
            data.setdefault("sensors", []).extend(feed_sensors.values())
        hass.data[DOMAIN]["free_drink_feed_sensors"] = feed_sensors

        async def _periodic_update(_now):
            for sensor in hass.data[DOMAIN]["free_drink_feed_sensors"].values():
                await sensor.async_update_state()

        hass.data[DOMAIN]["feed_unsub"] = async_track_time_interval(
            hass, _periodic_update, timedelta(seconds=60)
        )


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
        user_slug = get_user_slug(hass, entry.data[CONF_USER])
        self.entity_id = f"sensor.{user_slug}_{slugify(drink)}_count"
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
        user_slug = get_user_slug(hass, entry.data[CONF_USER])
        self.entity_id = f"sensor.{user_slug}_amount_due"
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


class FreeDrinkFeedSensor(SensorEntity):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, year: int, max_entries: int = 20
    ) -> None:
        self._hass = hass
        self._year = year
        self._max_entries = max_entries
        self._attr_should_poll = False
        self._attr_name = (
            f"{_local_suffix(hass, 'Free drinks feed', 'Freigetränke Feed')} {year}"
        )
        self.entity_id = f"sensor.free_drink_feed_{year}"
        self._attr_unique_id = f"{entry.entry_id}_free_drink_feed_{year}"
        self._path = hass.config.path(
            "backup", "tally_list", "free_drinks", f"free_drinks_{year}.csv"
        )
        self._entries: list[dict[str, str]] = []
        self._attr_native_value = "none"

    async def async_added_to_hass(self) -> None:
        await self.async_update_state()

    async def async_update_state(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8", newline="") as csvfile:
                reader = csv.reader(csvfile, delimiter=";")
                try:
                    next(reader)
                except StopIteration:
                    rows: list[list[str]] = []
                else:
                    rows = list(deque(reader, maxlen=self._max_entries))
        except FileNotFoundError:
            self._entries = []
            self._attr_native_value = "none"
            self.async_write_ha_state()
            return
        except OSError as err:
            _LOGGER.warning("Failed reading free drink log %s: %s", self._path, err)
            return

        entries: list[dict[str, str]] = []
        for row in reversed(rows):
            if len(row) != 4:
                _LOGGER.warning(
                    "Skipping malformed free drink row for %s: %s", self._year, row
                )
                continue
            try:
                dt = datetime.strptime(row[0], "%Y-%m-%dT%H:%M")
                time_local = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                _LOGGER.warning(
                    "Skipping free drink row with bad time for %s: %s", self._year, row
                )
                continue
            entries.append(
                {
                    "time_local": time_local,
                    "name": row[1],
                    "drinks": row[2].replace(" x", " ×").replace(",", " •"),
                    "comment": row[3],
                }
            )

        self._entries = entries
        if entries:
            self._attr_native_value = entries[0]["time_local"]
        else:
            self._attr_native_value = "none"
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, list[dict[str, str]]]:
        return {"entries": self._entries}
