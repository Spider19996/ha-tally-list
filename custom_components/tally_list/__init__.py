"""Tally List integration."""

from __future__ import annotations

import logging
import csv
import os
import re
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.util.dt import now as dt_now
from homeassistant.util import dt as dt_util
from homeassistant.helpers.storage import Store

from .websocket import async_register as async_register_ws
from .sensor import FreeDrinkFeedSensor
from .security import hash_pin, verify_pin
from .utils import get_person_name
from .config_flow import _log_price_change

from .const import (
    DOMAIN,
    SERVICE_ADD_DRINK,
    SERVICE_REMOVE_DRINK,
    SERVICE_ADJUST_COUNT,
    SERVICE_RESET_COUNTERS,
    SERVICE_EXPORT_CSV,
    SERVICE_SET_PIN,
    SERVICE_ADD_CREDIT,
    SERVICE_REMOVE_CREDIT,
    SERVICE_SET_CREDIT,
    ATTR_USER,
    ATTR_DRINK,
    CONF_USER,
    CONF_FREE_AMOUNT,
    CONF_EXCLUDED_USERS,
    CONF_OVERRIDE_USERS,
    CONF_PUBLIC_DEVICES,
    CONF_USER_PIN,
    CONF_USER_PINS,
    PRICE_LIST_USERS,
    CONF_CURRENCY,
    CONF_ICONS,
    CONF_ENABLE_FREE_DRINKS,
    CONF_CASH_USER_NAME,
    ATTR_FREE_DRINK,
    ATTR_COMMENT,
    ATTR_PIN,
    ATTR_AMOUNT,
    get_cash_user_name,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["sensor", "button"]
PINS_STORAGE_VERSION = 1
PINS_STORAGE_KEY = f"{DOMAIN}_pins"


async def _async_update_feed_sensor(hass: HomeAssistant) -> None:
    """Create or update the free drink feed sensor."""
    sensor = hass.data[DOMAIN].get("free_drink_feed_sensor")
    if sensor is not None:
        await sensor.async_update_state()
        return
    add_entities = hass.data[DOMAIN].get("feed_add_entities")
    feed_entry_id = hass.data[DOMAIN].get("feed_entry_id")
    entry = (
        hass.config_entries.async_get_entry(feed_entry_id)
        if feed_entry_id is not None
        else None
    )
    if add_entities is not None and entry is not None:
        sensor = FreeDrinkFeedSensor(hass, entry)
        hass.data[DOMAIN]["free_drink_feed_sensor"] = sensor
        add_entities([sensor])


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up via YAML is not supported."""
    hass.data.setdefault(
        DOMAIN,
        {
            "drinks": {},
            "drink_icons": {},
            CONF_EXCLUDED_USERS: [],
            CONF_OVERRIDE_USERS: [],
            CONF_PUBLIC_DEVICES: [],
            CONF_USER_PINS: {},
            CONF_CURRENCY: "€",
            CONF_ENABLE_FREE_DRINKS: False,
            CONF_CASH_USER_NAME: get_cash_user_name(hass.config.language),
            "free_drink_counts": {},
            "free_drinks_ledger": 0.0,
            "logins": {},
        },
    )

    store = Store(hass, PINS_STORAGE_VERSION, PINS_STORAGE_KEY, private=True)
    hass.data[DOMAIN]["pins_store"] = store
    stored_pins = await store.async_load() or {}
    hass.data[DOMAIN][CONF_USER_PINS] = stored_pins

    async def _verify_permissions(call, target_user: str | None) -> None:
        user_id = call.context.user_id
        if user_id is None:
            return
        hass_user = await hass.auth.async_get_user(user_id)
        if hass_user is None:
            return
        override_users = hass.data.get(DOMAIN, {}).get(CONF_OVERRIDE_USERS, [])
        public_devices = hass.data.get(DOMAIN, {}).get(CONF_PUBLIC_DEVICES, [])
        user_pins = hass.data.get(DOMAIN, {}).get(CONF_USER_PINS, {})
        logins = hass.data.get(DOMAIN, {}).get("logins", {})
        person_name = get_person_name(hass, hass_user.id)
        if person_name in override_users:
            return
        if person_name in public_devices and target_user:
            user_pin = user_pins.get(target_user)
            provided_pin = call.data.get(ATTR_PIN)
            verified = (
                provided_pin is not None
                and user_pin is not None
                and verify_pin(str(provided_pin), user_pin)
            )
            if user_pin and (verified or logins.get(user_id) == target_user):
                return
        if target_user is None:
            raise Unauthorized
        if person_name != target_user:
            raise Unauthorized

    def _write_free_drink_log(name: str, drink: str, count: int, comment: str) -> None:
        tz = dt_util.get_time_zone("Europe/Berlin")
        ts = dt_util.now(tz).replace(second=0, microsecond=0)
        base_dir = hass.config.path("tally_list", "free_drinks")
        os.makedirs(base_dir, exist_ok=True)
        year = ts.strftime("%Y")
        path = os.path.join(base_dir, f"free_drinks_{year}.csv")
        key_time = ts.strftime("%Y-%m-%dT%H:%M")
        comment_clean = re.sub(r"[\n\r\t]", " ", comment).strip()[:200]
        rows: list[list[str]] = []
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8", newline="") as csvfile:
                rows = list(csv.reader(csvfile, delimiter=";"))
        if not rows:
            rows = [["Uhrzeit", "Name", "Getränke mit Anzahl", "Kommentar"]]
        last_key = None
        if len(rows) > 1:
            last = rows[-1]
            last_key = (last[0], last[1], last[3])
        key = (key_time, name, comment_clean)
        if key == last_key:
            drink_map: dict[str, int] = {}
            if rows[-1][2]:
                for part in rows[-1][2].split(","):
                    part = part.strip()
                    if not part:
                        continue
                    dname, dcount = part.rsplit(" x", 1)
                    drink_map[dname] = int(dcount)
            drink_map[drink] = drink_map.get(drink, 0) + count
            drink_map = {k: v for k, v in drink_map.items() if v != 0}
            drink_str = ", ".join(
                f"{k} x{v}" for k, v in sorted(drink_map.items())
            )
            rows[-1][2] = drink_str
        else:
            drink_str = f"{drink} x{count}"
            rows.append([key_time, name, drink_str, comment_clean])
        with open(path, "w", encoding="utf-8", newline="") as csvfile:
            writer = csv.writer(csvfile, delimiter=";", quoting=csv.QUOTE_MINIMAL)
            writer.writerows(rows)

    def _find_user_entry(name: str) -> dict | None:
        for data in hass.data[DOMAIN].values():
            if (
                isinstance(data, dict)
                and "entry" in data
                and data["entry"].data.get(CONF_USER) == name
            ):
                return data
        return None

    def _find_cash_entry() -> dict:
        cash_name = hass.data[DOMAIN].get(CONF_CASH_USER_NAME)
        if not cash_name:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cash_user_missing"
            )
        entry = _find_user_entry(cash_name)
        if entry is None:
            cash_name_norm = cash_name.strip().lower()
            for data in hass.data[DOMAIN].values():
                if (
                    isinstance(data, dict)
                    and "entry" in data
                    and data["entry"].data.get(CONF_USER, "").strip().lower()
                    == cash_name_norm
                ):
                    entry = data
                    break
        if entry is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cash_user_missing"
            )
        return entry

    async def set_pin_service(call):
        user_id = call.context.user_id
        if user_id is None:
            raise Unauthorized
        hass_user = await hass.auth.async_get_user(user_id)
        if hass_user is None:
            raise Unauthorized
        person_name = get_person_name(hass, hass_user.id)
        if person_name is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="user_unknown"
            )

        target_user = call.data.get(ATTR_USER, person_name)
        if target_user != person_name:
            override_users = hass.data.get(DOMAIN, {}).get(CONF_OVERRIDE_USERS, [])
            if person_name not in override_users:
                raise Unauthorized

        pin = call.data.get(ATTR_PIN)
        user_pins = hass.data[DOMAIN].setdefault(CONF_USER_PINS, {})
        old_value = user_pins.get(target_user)
        if pin is not None and pin != "":
            pin = str(pin)
            if not re.fullmatch(r"\d{4}", pin):
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="invalid_pin"
                )
            user_pins[target_user] = hash_pin(pin)
        else:
            user_pins.pop(target_user, None)
        try:
            await hass.data[DOMAIN]["pins_store"].async_save(user_pins)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.error("Failed to save PIN for %s: %s", target_user, err)
            if old_value is None:
                user_pins.pop(target_user, None)
            else:
                user_pins[target_user] = old_value
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="pin_save_failed"
            ) from err
        await _log_price_change(
            hass,
            user_id,
            "set_pin",
            f"{target_user}:{'set' if pin else 'cleared'}",
        )

    async def adjust_count_service(call):
        user = call.data[ATTR_USER]
        await _verify_permissions(call, user)
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
        await _log_price_change(
            hass,
            call.context.user_id,
            "set_count",
            f"{user}:{drink}={count}",
        )

    async def add_drink_service(call):
        user = call.data[ATTR_USER]
        await _verify_permissions(call, user)
        drink = call.data[ATTR_DRINK]
        count = max(0, call.data.get("count", 1))
        free_drink = call.data.get(ATTR_FREE_DRINK, False)
        comment = call.data.get(ATTR_COMMENT, "")
        entry = _find_user_entry(user)
        if entry is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="user_unknown"
            )
        if free_drink:
            if not hass.data[DOMAIN].get(CONF_ENABLE_FREE_DRINKS):
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="free_drinks_disabled",
                )
            comment = comment.strip()
            if len(comment) < 3 or len(comment) > 200:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="comment_required"
                )
            if drink not in hass.data[DOMAIN].get("drinks", {}):
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="drink_unknown"
                )
            cash_entry = _find_cash_entry()
            counts = cash_entry.setdefault("counts", {})
            counts[drink] = counts.get(drink, 0) + count
            hass.data[DOMAIN]["free_drink_counts"] = counts
            for sensor in cash_entry.get("sensors", []):
                await sensor.async_update_state()
            price = hass.data[DOMAIN]["drinks"].get(drink, 0.0)
            hass.data[DOMAIN]["free_drinks_ledger"] = hass.data[DOMAIN].get(
                "free_drinks_ledger", 0.0
            ) + price * count
            await hass.async_add_executor_job(
                _write_free_drink_log, user, drink, count, comment
            )
            await _async_update_feed_sensor(hass)
            hass.bus.async_fire(
                "tally_list_free_drink_created",
                {"user": user, "drink": drink, "count": count, "comment": comment},
            )
            await _log_price_change(
                hass,
                call.context.user_id,
                "book_free_drink",
                f"{user}:{drink}+{count}",
            )
            return
        counts = entry.setdefault("counts", {})
        new_count = counts.get(drink, 0) + count
        counts[drink] = new_count
        for sensor in entry.get("sensors", []):
            await sensor.async_update_state()
        await _log_price_change(
            hass,
            call.context.user_id,
            "book_drink",
            f"{user}:{drink}+{count}",
        )

    async def remove_drink_service(call):
        user = call.data[ATTR_USER]
        await _verify_permissions(call, user)
        drink = call.data[ATTR_DRINK]
        count = max(0, call.data.get("count", 1))
        free_drink = call.data.get(ATTR_FREE_DRINK, False)
        comment = call.data.get(ATTR_COMMENT, "")
        if free_drink:
            if not hass.data[DOMAIN].get(CONF_ENABLE_FREE_DRINKS):
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="free_drinks_disabled",
                )
            cash_entry = _find_cash_entry()
            counts = cash_entry.setdefault("counts", {})
            if counts.get(drink, 0) < count:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="cannot_remove_count"
                )
            counts[drink] -= count
            for sensor in cash_entry.get("sensors", []):
                await sensor.async_update_state()
            price = hass.data[DOMAIN]["drinks"].get(drink, 0.0)
            hass.data[DOMAIN]["free_drinks_ledger"] = hass.data[DOMAIN].get(
                "free_drinks_ledger", 0.0
            ) - price * count
            comment = comment.strip()
            await hass.async_add_executor_job(
                _write_free_drink_log, user, drink, -count, comment
            )
            await _async_update_feed_sensor(hass)
            hass.bus.async_fire(
                "tally_list_free_drink_reversed",
                {"user": user, "drink": drink, "count": count, "comment": comment},
            )
            await _log_price_change(
                hass,
                call.context.user_id,
                "remove_free_drink",
                f"{user}:{drink}-{count}",
            )
            return
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict) or "entry" not in data:
                continue
            if data["entry"].data.get("user") == user:
                counts = data.setdefault("counts", {})
                new_count = counts.get(drink, 0) - count
                if new_count < 0:
                    new_count = 0
                counts[drink] = new_count
                for sensor in data.get("sensors", []):
                    await sensor.async_update_state()
                break
        await _log_price_change(
            hass,
            call.context.user_id,
            "remove_drink",
            f"{user}:{drink}-{count}",
        )

    async def add_credit_service(call):
        await _verify_permissions(call, None)
        user = call.data[ATTR_USER]
        amount = float(call.data.get(ATTR_AMOUNT, 0.0))
        entry = _find_user_entry(user)
        if entry is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="user_unknown"
            )
        entry["credit"] = entry.setdefault("credit", 0.0) + amount
        for sensor in entry.get("sensors", []):
            await sensor.async_update_state()
        await _log_price_change(
            hass,
            call.context.user_id,
            "add_credit",
            f"{user}:{amount}",
        )

    async def remove_credit_service(call):
        await _verify_permissions(call, None)
        user = call.data[ATTR_USER]
        amount = float(call.data.get(ATTR_AMOUNT, 0.0))
        entry = _find_user_entry(user)
        if entry is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="user_unknown"
            )
        entry["credit"] = entry.setdefault("credit", 0.0) - amount
        for sensor in entry.get("sensors", []):
            await sensor.async_update_state()
        await _log_price_change(
            hass,
            call.context.user_id,
            "remove_credit",
            f"{user}:{amount}",
        )

    async def set_credit_service(call):
        await _verify_permissions(call, None)
        user = call.data[ATTR_USER]
        amount = float(call.data.get(ATTR_AMOUNT, 0.0))
        entry = _find_user_entry(user)
        if entry is None:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="user_unknown"
            )
        entry["credit"] = amount
        for sensor in entry.get("sensors", []):
            await sensor.async_update_state()
        await _log_price_change(
            hass,
            call.context.user_id,
            "set_credit",
            f"{user}:{amount}",
        )

    async def reset_counters_service(call):
        user = call.data.get(ATTR_USER)
        await _verify_permissions(call, user)
        drinks = hass.data[DOMAIN].get("drinks", {})
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict) or "entry" not in data:
                continue
            if user is None or data["entry"].data.get("user") == user:
                data["counts"] = {drink: 0 for drink in drinks}
                data["credit"] = 0.0
                for sensor in data.get("sensors", []):
                    await sensor.async_update_state()
        if user is None or user == hass.data[DOMAIN].get(CONF_CASH_USER_NAME):
            hass.data[DOMAIN]["free_drink_counts"] = {}
            hass.data[DOMAIN]["free_drinks_ledger"] = 0.0
            base_dir = hass.config.path("tally_list", "free_drinks")
            if os.path.isdir(base_dir):
                for name in os.listdir(base_dir):
                    if not re.match(r"free_drinks_\d{4}\.csv$", name):
                        continue
                    path = os.path.join(base_dir, name)
                    try:
                        await hass.async_add_executor_job(os.remove, path)
                    except FileNotFoundError:
                        pass
            await _async_update_feed_sensor(hass)
        await _log_price_change(
            hass,
            call.context.user_id,
            "reset_counters",
            user if user is not None else "all",
        )

    async def export_csv_service(call):
        sensors = sorted(
            [
                state
                for state in hass.states.async_all("sensor")
                if state.entity_id.endswith("_amount_due")
            ],
            key=lambda state: state.name.casefold(),
        )
        currency = hass.data.get(DOMAIN, {}).get(CONF_CURRENCY, "€")
        now = dt_now()
        base_dir = hass.config.path("tally_list")

        def _write_csv(path: str) -> None:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(["Name", f"Betrag ({currency})"])
                for state in sensors:
                    try:
                        amount = float(state.state)
                    except (ValueError, TypeError):
                        amount = 0.0
                    name = state.name.replace(" Amount Due", "")
                    writer.writerow([name, f"{amount:.2f}"])
        def _cleanup(path: str, keep: int | None, unit: str) -> None:
            if keep is None or keep <= 0:
                return
            if unit == "files":
                if not os.path.isdir(path):
                    return
                files = [
                    os.path.join(path, fname)
                    for fname in os.listdir(path)
                    if os.path.isfile(os.path.join(path, fname))
                ]
                files.sort(key=os.path.getmtime, reverse=True)
                for file in files[keep:]:
                    os.remove(file)
                return
            days = keep
            if unit == "weeks":
                days *= 7
            elif unit == "months":
                days *= 30
            cutoff = now - timedelta(days=days)
            if not os.path.isdir(path):
                return
            for filename in os.listdir(path):
                file_path = os.path.join(path, filename)
                if not os.path.isfile(file_path):
                    continue
                mtime = datetime.fromtimestamp(
                    os.path.getmtime(file_path), tz=now.tzinfo
                )
                if mtime < cutoff:
                    os.remove(file_path)

        backup = call.data.get("backup")
        interval = call.data.get("interval", 1) or 1
        keep = call.data.get("keep")
        if keep is None:
            if backup == "daily":
                keep = 7
            elif backup == "weekly":
                keep = 30
            elif backup == "monthly":
                keep = 365
            elif backup == "manual":
                keep = 180

        if backup == "daily":
            if now.timetuple().tm_yday % interval == 0:
                file_path = os.path.join(
                    base_dir,
                    "daily",
                    f"amount_due_daily_{now.strftime('%Y-%m-%d_%H-%M')}.csv",
                )
                await hass.async_add_executor_job(_write_csv, file_path)
            await hass.async_add_executor_job(
                _cleanup, os.path.join(base_dir, "daily"), keep, "days"
            )
        elif backup == "weekly":
            iso_year, iso_week, _ = now.isocalendar()
            if iso_week % interval == 0:
                weekly_file = os.path.join(
                    base_dir,
                    "weekly",
                    f"amount_due_weekly_{iso_year}-{iso_week:02d}.csv",
                )
                if not os.path.exists(weekly_file):
                    await hass.async_add_executor_job(_write_csv, weekly_file)
            await hass.async_add_executor_job(
                _cleanup, os.path.join(base_dir, "weekly"), keep, "weeks"
            )
        elif backup == "monthly":
            if now.month % interval == 0:
                monthly_file = os.path.join(
                    base_dir,
                    "monthly",
                    f"amount_due_monthly_{now.strftime('%Y-%m')}.csv",
                )
                if not os.path.exists(monthly_file):
                    await hass.async_add_executor_job(_write_csv, monthly_file)
            await hass.async_add_executor_job(
                _cleanup, os.path.join(base_dir, "monthly"), keep, "months"
            )
        elif backup == "manual":
            manual_file = os.path.join(
                base_dir,
                "manual",
                f"amount_due_manual_{now.strftime('%Y-%m-%d_%H-%M')}.csv",
            )
            await hass.async_add_executor_job(_write_csv, manual_file)
            await hass.async_add_executor_job(
                _cleanup, os.path.join(base_dir, "manual"), keep, "files"
            )

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

    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPORT_CSV,
        export_csv_service,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PIN,
        set_pin_service,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_CREDIT,
        add_credit_service,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_CREDIT,
        remove_credit_service,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_CREDIT,
        set_credit_service,
    )

    await async_register_ws(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    hass.data.setdefault(
        DOMAIN,
        {
            "drinks": {},
            "drink_icons": {},
            CONF_EXCLUDED_USERS: [],
            CONF_OVERRIDE_USERS: [],
            CONF_CURRENCY: "€",
        },
    )
    hass.data[DOMAIN].setdefault(entry.entry_id, {"entry": entry, "counts": {}, "credit": 0.0})
    cash_name = get_cash_user_name(hass.config.language)
    hass.data[DOMAIN][CONF_CASH_USER_NAME] = cash_name
    if entry.data.get(CONF_CASH_USER_NAME) != cash_name:
        entry_data = dict(entry.data)
        entry_data[CONF_CASH_USER_NAME] = cash_name
        hass.config_entries.async_update_entry(entry, data=entry_data)
    if (
        cash_name
        and entry.data.get(CONF_USER, "").strip().lower() == cash_name.strip().lower()
    ):
        hass.data[DOMAIN]["free_drink_counts"] = hass.data[DOMAIN][entry.entry_id][
            "counts"
        ]
    if not hass.data[DOMAIN].get("drinks") and entry.data.get("drinks"):
        hass.data[DOMAIN]["drinks"] = entry.data["drinks"]
    if not hass.data[DOMAIN].get("drink_icons") and entry.data.get(CONF_ICONS):
        hass.data[DOMAIN]["drink_icons"] = entry.data[CONF_ICONS]
    if hass.data[DOMAIN].get("drinks") and not entry.data.get("drinks"):
        entry_data = {
            "user": entry.data.get("user"),
            CONF_FREE_AMOUNT: hass.data[DOMAIN].get("free_amount", 0.0),
            CONF_EXCLUDED_USERS: hass.data[DOMAIN].get("excluded_users", []),
            CONF_OVERRIDE_USERS: hass.data[DOMAIN].get("override_users", []),
            CONF_CURRENCY: hass.data[DOMAIN].get(CONF_CURRENCY, "€"),
        }
        if "drinks" in hass.data[DOMAIN]:
            entry_data["drinks"] = hass.data[DOMAIN]["drinks"]
        if "drink_icons" in hass.data[DOMAIN]:
            entry_data[CONF_ICONS] = hass.data[DOMAIN]["drink_icons"]
        hass.config_entries.async_update_entry(entry, data=entry_data)
    if hass.data[DOMAIN].get("drink_icons") and not entry.data.get(CONF_ICONS):
        entry_data = dict(entry.data)
        entry_data[CONF_ICONS] = hass.data[DOMAIN]["drink_icons"]
        if "drinks" in hass.data[DOMAIN] and "drinks" not in entry_data:
            entry_data["drinks"] = hass.data[DOMAIN]["drinks"]
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
            CONF_FREE_AMOUNT: hass.data[DOMAIN]["free_amount"],
            CONF_EXCLUDED_USERS: hass.data[DOMAIN].get("excluded_users", []),
            CONF_OVERRIDE_USERS: hass.data[DOMAIN].get("override_users", []),
            CONF_CURRENCY: hass.data[DOMAIN].get(CONF_CURRENCY, "€"),
        }
        if "drinks" in hass.data[DOMAIN]:
            entry_data["drinks"] = hass.data[DOMAIN]["drinks"]
        if "drink_icons" in hass.data[DOMAIN]:
            entry_data[CONF_ICONS] = hass.data[DOMAIN]["drink_icons"]
        hass.config_entries.async_update_entry(entry, data=entry_data)
    if (
        not hass.data[DOMAIN].get("excluded_users")
        and entry.data.get(CONF_EXCLUDED_USERS) is not None
    ):
        hass.data[DOMAIN]["excluded_users"] = entry.data[CONF_EXCLUDED_USERS]
    if (
        not hass.data[DOMAIN].get("override_users")
        and entry.data.get(CONF_OVERRIDE_USERS) is not None
    ):
        hass.data[DOMAIN]["override_users"] = entry.data[CONF_OVERRIDE_USERS]
    if (
        hass.data[DOMAIN].get("excluded_users") is not None
        and CONF_EXCLUDED_USERS not in entry.data
    ):
        entry_data = {
            "user": entry.data.get("user"),
            CONF_FREE_AMOUNT: hass.data[DOMAIN].get("free_amount", 0.0),
            CONF_EXCLUDED_USERS: hass.data[DOMAIN]["excluded_users"],
            CONF_OVERRIDE_USERS: hass.data[DOMAIN].get("override_users", []),
            CONF_CURRENCY: hass.data[DOMAIN].get(CONF_CURRENCY, "€"),
        }
        if "drinks" in hass.data[DOMAIN]:
            entry_data["drinks"] = hass.data[DOMAIN]["drinks"]
        if "drink_icons" in hass.data[DOMAIN]:
            entry_data[CONF_ICONS] = hass.data[DOMAIN]["drink_icons"]
        hass.config_entries.async_update_entry(entry, data=entry_data)
    if (
        hass.data[DOMAIN].get("override_users") is not None
        and CONF_OVERRIDE_USERS not in entry.data
    ):
        entry_data = {
            "user": entry.data.get("user"),
            CONF_FREE_AMOUNT: hass.data[DOMAIN].get("free_amount", 0.0),
            CONF_EXCLUDED_USERS: hass.data[DOMAIN].get("excluded_users", []),
            CONF_OVERRIDE_USERS: hass.data[DOMAIN]["override_users"],
            CONF_CURRENCY: hass.data[DOMAIN].get(CONF_CURRENCY, "€"),
        }
        if "drinks" in hass.data[DOMAIN]:
            entry_data["drinks"] = hass.data[DOMAIN]["drinks"]
        if "drink_icons" in hass.data[DOMAIN]:
            entry_data[CONF_ICONS] = hass.data[DOMAIN]["drink_icons"]
        hass.config_entries.async_update_entry(entry, data=entry_data)
    if (
        not hass.data[DOMAIN].get(CONF_CURRENCY)
        and entry.data.get(CONF_CURRENCY) is not None
    ):
        hass.data[DOMAIN][CONF_CURRENCY] = entry.data[CONF_CURRENCY]
    if (
        hass.data[DOMAIN].get(CONF_CURRENCY) is not None
        and CONF_CURRENCY not in entry.data
    ):
        entry_data = {
            "user": entry.data.get("user"),
            CONF_FREE_AMOUNT: hass.data[DOMAIN].get("free_amount", 0.0),
            CONF_EXCLUDED_USERS: hass.data[DOMAIN].get("excluded_users", []),
            CONF_OVERRIDE_USERS: hass.data[DOMAIN].get("override_users", []),
            CONF_CURRENCY: hass.data[DOMAIN][CONF_CURRENCY],
            CONF_ENABLE_FREE_DRINKS: hass.data[DOMAIN].get(CONF_ENABLE_FREE_DRINKS, False),
            CONF_CASH_USER_NAME: hass.data[DOMAIN].get(
                CONF_CASH_USER_NAME, get_cash_user_name(hass.config.language)
            ),
        }
        if "drinks" in hass.data[DOMAIN]:
            entry_data["drinks"] = hass.data[DOMAIN]["drinks"]
        if "drink_icons" in hass.data[DOMAIN]:
            entry_data[CONF_ICONS] = hass.data[DOMAIN]["drink_icons"]
        hass.config_entries.async_update_entry(entry, data=entry_data)
    if (
        not hass.data[DOMAIN].get(CONF_ENABLE_FREE_DRINKS)
        and entry.data.get(CONF_ENABLE_FREE_DRINKS) is not None
    ):
        hass.data[DOMAIN][CONF_ENABLE_FREE_DRINKS] = entry.data[CONF_ENABLE_FREE_DRINKS]
    if (
        (hass.data[DOMAIN].get(CONF_ENABLE_FREE_DRINKS) is not None
         and CONF_ENABLE_FREE_DRINKS not in entry.data)
        or (
            hass.data[DOMAIN].get(CONF_CASH_USER_NAME) is not None
            and CONF_CASH_USER_NAME not in entry.data
        )
    ):
        entry_data = {
            "user": entry.data.get("user"),
            CONF_FREE_AMOUNT: hass.data[DOMAIN].get("free_amount", 0.0),
            CONF_EXCLUDED_USERS: hass.data[DOMAIN].get("excluded_users", []),
            CONF_OVERRIDE_USERS: hass.data[DOMAIN].get("override_users", []),
            CONF_CURRENCY: hass.data[DOMAIN].get(CONF_CURRENCY, "€"),
            CONF_ENABLE_FREE_DRINKS: hass.data[DOMAIN].get(
                CONF_ENABLE_FREE_DRINKS, False
            ),
            CONF_CASH_USER_NAME: hass.data[DOMAIN].get(
                CONF_CASH_USER_NAME, get_cash_user_name(hass.config.language)
            ),
        }
        if "drinks" in hass.data[DOMAIN]:
            entry_data["drinks"] = hass.data[DOMAIN]["drinks"]
        if "drink_icons" in hass.data[DOMAIN]:
            entry_data[CONF_ICONS] = hass.data[DOMAIN]["drink_icons"]
        hass.config_entries.async_update_entry(entry, data=entry_data)
    if entry.data.get(CONF_PUBLIC_DEVICES) is not None:
        hass.data[DOMAIN][CONF_PUBLIC_DEVICES] = entry.data[CONF_PUBLIC_DEVICES]
    elif hass.data[DOMAIN].get(CONF_PUBLIC_DEVICES) is not None:
        entry_data = dict(entry.data)
        entry_data[CONF_PUBLIC_DEVICES] = hass.data[DOMAIN][CONF_PUBLIC_DEVICES]
        hass.config_entries.async_update_entry(entry, data=entry_data)
    user_name = entry.data.get(CONF_USER)
    if user_name and entry.data.get(CONF_USER_PIN) is not None:
        pin = entry.data[CONF_USER_PIN]
        hass.data[DOMAIN][CONF_USER_PINS][user_name] = pin
        await hass.data[DOMAIN]["pins_store"].async_save(
            hass.data[DOMAIN][CONF_USER_PINS]
        )
        entry_data = dict(entry.data)
        entry_data.pop(CONF_USER_PIN, None)
        hass.config_entries.async_update_entry(entry, data=entry_data)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unloaded:
        if hass.data[DOMAIN].get("feed_entry_id") == entry.entry_id:
            unsub = hass.data[DOMAIN].pop("feed_unsub", None)
            if unsub is not None:
                unsub()
            hass.data[DOMAIN].pop("free_drink_feed_sensor", None)
            hass.data[DOMAIN].pop("feed_add_entities", None)
            hass.data[DOMAIN].pop("feed_entry_id", None)
        if hass.data[DOMAIN].get("price_feed_entry_id") == entry.entry_id:
            unsub = hass.data[DOMAIN].pop("price_feed_unsub", None)
            if unsub is not None:
                unsub()
            hass.data[DOMAIN].pop("price_list_feed_sensor", None)
            hass.data[DOMAIN].pop("price_feed_add_entities", None)
            hass.data[DOMAIN].pop("price_feed_entry_id", None)
        hass.data[DOMAIN].pop(entry.entry_id, None)
        user_name = entry.data.get(CONF_USER)
        if user_name in PRICE_LIST_USERS:
            hass.data[DOMAIN].pop("drinks", None)
            hass.data[DOMAIN].pop("drink_icons", None)
            hass.data[DOMAIN].pop("free_amount", None)
            # Keep excluded users so they are not re-created when the price list
            # user is re-added later
            hass.data[DOMAIN].pop(CONF_OVERRIDE_USERS, None)
            hass.data[DOMAIN].pop(CONF_CURRENCY, None)
            hass.data[DOMAIN].pop(CONF_ENABLE_FREE_DRINKS, None)
            hass.data[DOMAIN].pop(CONF_CASH_USER_NAME, None)
            hass.data[DOMAIN].pop("free_drinks_ledger", None)
        elif (
            hass.data[DOMAIN].get(CONF_CASH_USER_NAME)
            and entry.data.get(CONF_USER, "").strip().lower()
            == hass.data[DOMAIN][CONF_CASH_USER_NAME].strip().lower()
        ):
            hass.data[DOMAIN].pop("free_drink_counts", None)
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of a config entry."""
    user_name = entry.data.get(CONF_USER)
    if user_name and CONF_USER_PINS in hass.data.get(DOMAIN, {}):
        hass.data[DOMAIN][CONF_USER_PINS].pop(user_name, None)
        await hass.data[DOMAIN]["pins_store"].async_save(
            hass.data[DOMAIN][CONF_USER_PINS]
        )
    if not hass.config_entries.async_entries(DOMAIN):
        hass.data.pop(DOMAIN, None)
