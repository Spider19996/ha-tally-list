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
    icons = hass.data[DOMAIN].get("drink_icons", {})
    sensors: list[SensorEntity] = []

    if user in PRICE_LIST_USERS:
        for drink_name, price in drinks.items():
            sensors.append(
                DrinkPriceSensor(
                    hass, entry, drink_name, price, icons.get(drink_name)
                )
            )
        sensors.append(FreeAmountSensor(hass, entry))
    else:
        for drink_name, price in drinks.items():
            sensors.append(
                TallyListSensor(hass, entry, drink_name, price, icons.get(drink_name))
            )
        sensors.append(TotalAmountSensor(hass, entry))
        sensors.append(CreditSensor(hass, entry))

    data.setdefault("sensors", []).extend(sensors)
    async_add_entities(sensors)

    cash_name = hass.data.get(DOMAIN, {}).get(CONF_CASH_USER_NAME, "")
    if (
        user.strip().lower() == cash_name.strip().lower()
        and "feed_add_entities" not in hass.data[DOMAIN]
    ):
        hass.data[DOMAIN]["feed_add_entities"] = async_add_entities
        hass.data[DOMAIN]["feed_entry_id"] = entry.entry_id
        feed_sensor = FreeDrinkFeedSensor(hass, entry)
        async_add_entities([feed_sensor])
        data.setdefault("sensors", []).append(feed_sensor)
        hass.data[DOMAIN]["free_drink_feed_sensor"] = feed_sensor

        async def _periodic_update(_now):
            sensor = hass.data[DOMAIN].get("free_drink_feed_sensor")
            if sensor is not None:
                await sensor.async_update_state()

        hass.data[DOMAIN]["feed_unsub"] = async_track_time_interval(
            hass, _periodic_update, timedelta(seconds=60)
        )

    if (
        user in PRICE_LIST_USERS
        and "price_feed_add_entities" not in hass.data[DOMAIN]
    ):
        hass.data[DOMAIN]["price_feed_add_entities"] = async_add_entities
        hass.data[DOMAIN]["price_feed_entry_id"] = entry.entry_id
        price_sensor = PriceListFeedSensor(hass, entry)
        async_add_entities([price_sensor])
        data.setdefault("sensors", []).append(price_sensor)
        hass.data[DOMAIN]["price_list_feed_sensor"] = price_sensor

        async def _price_periodic_update(_now):
            sensor = hass.data[DOMAIN].get("price_list_feed_sensor")
            if sensor is not None:
                await sensor.async_update_state()

        hass.data[DOMAIN]["price_feed_unsub"] = async_track_time_interval(
            hass, _price_periodic_update, timedelta(seconds=60)
        )


class TallyListSensor(RestoreEntity, SensorEntity):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        drink: str,
        price: float,
        icon: str | None = None,
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
        self._attr_native_unit_of_measurement = ""
        self._attr_icon = icon

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
        self._attr_native_unit_of_measurement = ""
        self.async_write_ha_state()

    @property
    def native_value(self):
        counts = self._hass.data[DOMAIN][self._entry.entry_id].setdefault(
            "counts",
            {},
        )
        return counts.get(self._drink, 0)


class CurrencySensor(SensorEntity):
    """Base class for sensors that use the configured currency."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._attr_should_poll = False
        self._attr_native_unit_of_measurement = hass.data.get(DOMAIN, {}).get(
            CONF_CURRENCY, "€"
        )

    async def async_added_to_hass(self) -> None:  # pragma: no cover - simple forwarding
        await super().async_added_to_hass()
        await self.async_update_state()

    async def async_update_state(self):
        self._attr_native_unit_of_measurement = self._hass.data.get(
            DOMAIN, {}
        ).get(CONF_CURRENCY, "€")
        self.async_write_ha_state()


class DrinkPriceSensor(CurrencySensor):
    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        drink: str,
        price: float,
        icon: str | None = None,
    ) -> None:
        super().__init__(hass)
        self._entry = entry
        self._drink = drink
        self._price = price
        self._attr_name = (
            f"{entry.data[CONF_USER]} {drink} "
            f"{_local_suffix(hass, 'Price', 'Preis')}"
        )
        self._attr_unique_id = f"{entry.entry_id}_{drink}_price"
        self.entity_id = f"sensor.price_list_{slugify(drink)}_price"
        self._attr_suggested_display_precision = 2
        self._attr_icon = icon

    @property
    def native_value(self):
        drinks = self._hass.data.get(DOMAIN, {}).get("drinks", {})
        return round(drinks.get(self._drink, self._price), 2)


class FreeAmountSensor(CurrencySensor):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass)
        self._entry = entry
        self._attr_name = (
            f"{entry.data[CONF_USER]} "
            f"{_local_suffix(hass, 'Free amount', 'Freibetrag')}"
        )
        self._attr_unique_id = f"{entry.entry_id}_free_amount"
        self.entity_id = "sensor.price_list_free_amount"
        self._attr_suggested_display_precision = 2
        self._attr_icon = "mdi:star"

    @property
    def icon(self) -> str:
        """Return the icon for the free amount sensor."""
        return "mdi:star"

    @property
    def native_value(self):
        return round(self._hass.data.get(DOMAIN, {}).get("free_amount", 0.0), 2)


class TotalAmountSensor(CurrencySensor, RestoreEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass)
        self._entry = entry
        self._attr_name = (
            f"{entry.data[CONF_USER]} "
            f"{_local_suffix(hass, 'Amount due', 'Offener Betrag')}"
        )
        self._attr_unique_id = f"{entry.entry_id}_amount_due"
        user_slug = get_user_slug(hass, entry.data[CONF_USER])
        self.entity_id = f"sensor.{user_slug}_amount_due"
        self._attr_native_value = 0
        self._attr_suggested_display_precision = 2
        self._attr_icon = "mdi:cash"

    @property
    def icon(self) -> str:
        """Return the icon for the total amount sensor."""
        return "mdi:cash"

    @property
    def native_value(self):
        data = self._hass.data[DOMAIN][self._entry.entry_id]
        counts = data.setdefault("counts", {})
        total = 0.0
        drinks = self._hass.data[DOMAIN].get("drinks", {})
        for drink, price in drinks.items():
            total += counts.get(drink, 0) * price
        user = self._entry.data[CONF_USER]
        cash_name = self._hass.data.get(DOMAIN, {}).get(CONF_CASH_USER_NAME, "")
        if user.strip().lower() != cash_name.strip().lower():
            free_amount = self._hass.data.get(DOMAIN, {}).get("free_amount", 0.0)
            total -= free_amount
            if total < 0:
                total = 0.0
        credit = data.get("credit", 0.0)
        total -= credit
        return round(total, 2)


class CreditSensor(CurrencySensor, RestoreEntity):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass)
        self._entry = entry
        self._attr_name = (
            f"{entry.data[CONF_USER]} "
            f"{_local_suffix(hass, 'Credit', 'Guthaben')}"
        )
        self._attr_unique_id = f"{entry.entry_id}_credit"
        user_slug = get_user_slug(hass, entry.data[CONF_USER])
        self.entity_id = f"sensor.{user_slug}_credit"
        self._attr_native_value = 0.0
        self._attr_suggested_display_precision = 2
        self._attr_icon = "mdi:bank"

    @property
    def icon(self) -> str:
        """Return the icon for the credit sensor."""
        return "mdi:bank"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state and last_state.state not in (None, "unknown", "unavailable"):
            try:
                restored = float(last_state.state)
            except ValueError:
                restored = 0.0
            data = self._hass.data[DOMAIN][self._entry.entry_id]
            data["credit"] = restored
            self._attr_native_value = restored
        await self.async_update_state()

    @property
    def native_value(self):
        data = self._hass.data[DOMAIN][self._entry.entry_id]
        return round(data.get("credit", 0.0), 2)


class FreeDrinkFeedSensor(SensorEntity):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, max_entries: int = 20
    ) -> None:
        self._hass = hass
        self._max_entries = max_entries
        self._attr_should_poll = False
        self._attr_name = _local_suffix(
            hass, "Free drinks feed", "Freigetränke Feed"
        )
        self.entity_id = "sensor.free_drink_feed"
        self._attr_unique_id = f"{entry.entry_id}_free_drink_feed"
        self._base_dir = hass.config.path("backup", "tally_list", "free_drinks")
        self._entries: list[dict[str, str]] = []
        self._attr_native_value = "none"
        self._attr_icon = "mdi:clipboard-list"

    @property
    def icon(self) -> str:
        """Return the icon for the free drink feed sensor."""
        return "mdi:clipboard-list"

    async def async_added_to_hass(self) -> None:
        await self.async_update_state()

    def _read_rows(self) -> list[list[str]]:
        rows: list[list[str]] = []
        if not os.path.isdir(self._base_dir):
            return rows
        for name in os.listdir(self._base_dir):
            if not re.match(r"free_drinks_\d{4}\.csv$", name):
                continue
            path = os.path.join(self._base_dir, name)
            with open(path, "r", encoding="utf-8", newline="") as csvfile:
                reader = csv.reader(csvfile, delimiter=";")
                try:
                    next(reader)
                except StopIteration:
                    continue
                rows.extend(list(reader))
        rows.sort(key=lambda r: r[0])
        return list(deque(rows, maxlen=self._max_entries))

    async def async_update_state(self) -> None:
        try:
            rows = await self._hass.async_add_executor_job(self._read_rows)
        except OSError as err:
            _LOGGER.warning(
                "Failed reading free drink logs %s: %s", self._base_dir, err
            )
            return

        entries: list[dict[str, str]] = []
        for row in reversed(rows):
            if len(row) != 4:
                _LOGGER.warning("Skipping malformed free drink row: %s", row)
                continue
            try:
                dt = datetime.strptime(row[0], "%Y-%m-%dT%H:%M")
                time_local = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                _LOGGER.warning(
                    "Skipping free drink row with bad time: %s", row
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


class PriceListFeedSensor(SensorEntity):
    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, max_entries: int = 20
    ) -> None:
        self._hass = hass
        self._max_entries = max_entries
        self._attr_should_poll = False
        self._attr_name = _local_suffix(hass, "Price list feed", "Preisliste Feed")
        self.entity_id = "sensor.price_list_feed"
        self._attr_unique_id = f"{entry.entry_id}_price_list_feed"
        self._base_dir = hass.config.path("backup", "tally_list", "price_list")
        self._entries: list[dict[str, str]] = []
        self._attr_native_value = "none"
        self._attr_icon = "mdi:clipboard-edit"

    @property
    def icon(self) -> str:
        """Return the icon for the price list feed sensor."""
        return "mdi:clipboard-edit"

    async def async_added_to_hass(self) -> None:
        await self.async_update_state()

    def _read_rows(self) -> list[list[str]]:
        rows: list[list[str]] = []
        if not os.path.isdir(self._base_dir):
            return rows
        for name in os.listdir(self._base_dir):
            if not re.match(r"price_list_\d{4}\.csv$", name):
                continue
            path = os.path.join(self._base_dir, name)
            with open(path, "r", encoding="utf-8", newline="") as csvfile:
                reader = csv.reader(csvfile, delimiter=";")
                try:
                    next(reader)
                except StopIteration:
                    continue
                rows.extend(list(reader))
        return rows

    async def async_update_state(self) -> None:
        try:
            rows = await self._hass.async_add_executor_job(self._read_rows)
        except OSError as err:
            _LOGGER.warning(
                "Failed reading price list logs %s: %s", self._base_dir, err
            )
            return

        entries: list[dict[str, str]] = []
        for row in rows:
            if len(row) != 4:
                _LOGGER.warning("Skipping malformed price list row: %s", row)
                continue
            try:
                dt = datetime.strptime(row[0], "%Y-%m-%dT%H:%M")
                time_local = dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                _LOGGER.warning("Skipping price list row with bad time: %s", row)
                continue
            entries.append(
                {
                    "time_local": time_local,
                    "user": row[1],
                    "action": row[2],
                    "details": row[3],
                    "dt": dt,
                }
            )

        entries.sort(key=lambda e: e["dt"], reverse=True)
        entries = entries[: self._max_entries]
        self._entries = [
            {k: v for k, v in entry.items() if k != "dt"} for entry in entries
        ]
        self._attr_native_value = (
            self._entries[0]["time_local"] if self._entries else "none"
        )
        self.async_write_ha_state()

    @property
    def extra_state_attributes(self) -> dict[str, list[dict[str, str]]]:
        return {"entries": self._entries}
