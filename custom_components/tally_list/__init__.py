"""Tally List integration."""

from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import Unauthorized, HomeAssistantError
from homeassistant.util.dt import now as dt_now

from .websocket import async_register as async_register_ws

from .const import (
    DOMAIN,
    SERVICE_ADD_DRINK,
    SERVICE_REMOVE_DRINK,
    SERVICE_ADJUST_COUNT,
    SERVICE_RESET_COUNTERS,
    SERVICE_EXPORT_CSV,
    ATTR_USER,
    ATTR_DRINK,
    CONF_USER,
    CONF_FREE_AMOUNT,
    CONF_EXCLUDED_USERS,
    CONF_OVERRIDE_USERS,
    PRICE_LIST_USERS,
    CONF_CURRENCY,
    CONF_ENABLE_FREE_MARKS,
    CONF_CASH_USER_NAME,
    EVENT_FREE_MARK_CREATED,
    EVENT_FREE_MARK_REVERSED,
    ERROR_FREE_MARKS_DISABLED,
    ERROR_COMMENT_REQUIRED,
    ERROR_CASH_USER_MISSING,
    ERROR_CANNOT_REMOVE_COUNT,
    ERROR_DRINK_UNKNOWN,
    get_cash_user_name,
)

PLATFORMS: list[str] = ["sensor", "button"]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up via YAML is not supported."""
    hass.data.setdefault(
        DOMAIN,
        {
            "drinks": {},
            CONF_EXCLUDED_USERS: [],
            CONF_OVERRIDE_USERS: [],
            CONF_CURRENCY: "€",
            CONF_ENABLE_FREE_MARKS: False,
            CONF_CASH_USER_NAME: get_cash_user_name(hass.config.language),
        },
    )
    hass.data[DOMAIN].setdefault("free_ledger", {})
    hass.data[DOMAIN].setdefault("free_ledger_total", 0.0)

    async def _verify_permissions(call, target_user: str | None) -> None:
        user_id = call.context.user_id
        if user_id is None:
            return
        hass_user = await hass.auth.async_get_user(user_id)
        if hass_user is None:
            return
        override_users = hass.data.get(DOMAIN, {}).get(CONF_OVERRIDE_USERS, [])
        person_name = None
        for state in hass.states.async_all("person"):
            if state.attributes.get("user_id") == hass_user.id:
                person_name = state.name
                break
        if person_name in override_users:
            return
        if target_user is None:
            raise Unauthorized
        if person_name != target_user:
            raise Unauthorized

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

    async def add_drink_service(call):
        user = call.data[ATTR_USER]
        await _verify_permissions(call, user)
        drink = call.data[ATTR_DRINK]
        count = max(0, call.data.get("count", 1))
        if call.data.get("free_mark"):
            if not hass.data[DOMAIN].get(CONF_ENABLE_FREE_MARKS):
                raise HomeAssistantError(ERROR_FREE_MARKS_DISABLED)
            comment = call.data.get("comment", "").strip()
            if len(comment) < 3 or len(comment) > 200:
                raise HomeAssistantError(ERROR_COMMENT_REQUIRED)
            cash_user = hass.data[DOMAIN].get("cash_user")
            if not cash_user:
                raise HomeAssistantError(ERROR_CASH_USER_MISSING)
            price = hass.data[DOMAIN].get("drinks", {}).get(drink)
            if price is None:
                raise HomeAssistantError(ERROR_DRINK_UNKNOWN)
            ledger = hass.data[DOMAIN].setdefault("free_ledger", {})
            drink_ledger = ledger.setdefault(drink, [])
            drink_ledger.append({"price": price, "count": count})
            hass.data[DOMAIN]["free_ledger_total"] = (
                hass.data[DOMAIN].get("free_ledger_total", 0.0)
                + price * count
            )
            counts = cash_user.setdefault("counts", {})
            counts[drink] = counts.get(drink, 0) + count
            hass.bus.async_fire(
                EVENT_FREE_MARK_CREATED,
                {
                    ATTR_USER: user,
                    ATTR_DRINK: drink,
                    "count": count,
                    "comment": comment,
                    "price": price,
                },
            )
            return
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict) or "entry" not in data:
                continue
            if data["entry"].data.get("user") == user:
                counts = data.setdefault("counts", {})
                new_count = counts.get(drink, 0) + count
                counts[drink] = new_count
                for sensor in data.get("sensors", []):
                    await sensor.async_update_state()
                break

    async def remove_drink_service(call):
        user = call.data[ATTR_USER]
        await _verify_permissions(call, user)
        drink = call.data[ATTR_DRINK]
        count = max(0, call.data.get("count", 1))
        if call.data.get("free_mark"):
            if not hass.data[DOMAIN].get(CONF_ENABLE_FREE_MARKS):
                raise HomeAssistantError(ERROR_FREE_MARKS_DISABLED)
            cash_user = hass.data[DOMAIN].get("cash_user")
            if not cash_user:
                raise HomeAssistantError(ERROR_CASH_USER_MISSING)
            price = hass.data[DOMAIN].get("drinks", {}).get(drink)
            if price is None:
                raise HomeAssistantError(ERROR_DRINK_UNKNOWN)
            ledger = hass.data[DOMAIN].setdefault("free_ledger", {})
            drink_ledger = ledger.get(drink, [])
            remaining = count
            refund = 0.0
            while drink_ledger and remaining > 0:
                entry = drink_ledger[0]
                if entry["count"] > remaining:
                    entry["count"] -= remaining
                    refund += entry["price"] * remaining
                    remaining = 0
                else:
                    refund += entry["price"] * entry["count"]
                    remaining -= entry["count"]
                    drink_ledger.pop(0)
            if remaining > 0:
                raise HomeAssistantError(ERROR_CANNOT_REMOVE_COUNT)
            counts = cash_user.setdefault("counts", {})
            current = counts.get(drink, 0)
            if current < count:
                raise HomeAssistantError(ERROR_CANNOT_REMOVE_COUNT)
            counts[drink] = current - count
            hass.data[DOMAIN]["free_ledger_total"] = (
                hass.data[DOMAIN].get("free_ledger_total", 0.0) - refund
            )
            hass.bus.async_fire(
                EVENT_FREE_MARK_REVERSED,
                {ATTR_USER: user, ATTR_DRINK: drink, "count": count, "price": price},
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

    async def reset_counters_service(call):
        user = call.data.get(ATTR_USER)
        await _verify_permissions(call, user)
        drinks = hass.data[DOMAIN].get("drinks", {})
        for entry_id, data in hass.data[DOMAIN].items():
            if not isinstance(data, dict) or "entry" not in data:
                continue
            if user is None or data["entry"].data.get("user") == user:
                data["counts"] = {drink: 0 for drink in drinks}
                for sensor in data.get("sensors", []):
                    await sensor.async_update_state()

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
        base_dir = hass.config.path("backup", "tally_list")

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

    await async_register_ws(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry."""
    hass.data.setdefault(
        DOMAIN,
        {
            "drinks": {},
            CONF_EXCLUDED_USERS: [],
            CONF_OVERRIDE_USERS: [],
            CONF_CURRENCY: "€",
        },
    )
    hass.data[DOMAIN].setdefault(entry.entry_id, {"entry": entry, "counts": {}})
    if not hass.data[DOMAIN].get("drinks") and entry.data.get("drinks"):
        hass.data[DOMAIN]["drinks"] = entry.data["drinks"]
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
        }
        if "drinks" in hass.data[DOMAIN]:
            entry_data["drinks"] = hass.data[DOMAIN]["drinks"]
        hass.config_entries.async_update_entry(entry, data=entry_data)
    if (
        not hass.data[DOMAIN].get(CONF_ENABLE_FREE_MARKS)
        and entry.data.get(CONF_ENABLE_FREE_MARKS) is not None
    ):
        hass.data[DOMAIN][CONF_ENABLE_FREE_MARKS] = entry.data[
            CONF_ENABLE_FREE_MARKS
        ]
    if (
        hass.data[DOMAIN].get(CONF_ENABLE_FREE_MARKS) is not None
        and CONF_ENABLE_FREE_MARKS not in entry.data
    ):
        entry_data = {
            "user": entry.data.get("user"),
            CONF_FREE_AMOUNT: hass.data[DOMAIN].get("free_amount", 0.0),
            CONF_EXCLUDED_USERS: hass.data[DOMAIN].get("excluded_users", []),
            CONF_OVERRIDE_USERS: hass.data[DOMAIN].get("override_users", []),
            CONF_CURRENCY: hass.data[DOMAIN].get(CONF_CURRENCY, "€"),
            CONF_ENABLE_FREE_MARKS: hass.data[DOMAIN].get(
                CONF_ENABLE_FREE_MARKS, False
            ),
            CONF_CASH_USER_NAME: hass.data[DOMAIN].get(
                CONF_CASH_USER_NAME, get_cash_user_name(hass.config.language)
            ),
        }
        if "drinks" in hass.data[DOMAIN]:
            entry_data["drinks"] = hass.data[DOMAIN]["drinks"]
        hass.config_entries.async_update_entry(entry, data=entry_data)
    if (
        not hass.data[DOMAIN].get(CONF_CASH_USER_NAME)
        and entry.data.get(CONF_CASH_USER_NAME) is not None
    ):
        hass.data[DOMAIN][CONF_CASH_USER_NAME] = entry.data[CONF_CASH_USER_NAME]
    if hass.data[DOMAIN].get(CONF_ENABLE_FREE_MARKS):
        hass.data[DOMAIN].setdefault(
            "cash_user",
            {"name": hass.data[DOMAIN][CONF_CASH_USER_NAME], "counts": {}},
        )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if entry.data.get(CONF_USER) in PRICE_LIST_USERS:
            hass.data[DOMAIN].pop("drinks", None)
            hass.data[DOMAIN].pop("free_amount", None)
            # Keep excluded users so they are not re-created when the price list
            # user is re-added later
            hass.data[DOMAIN].pop(CONF_OVERRIDE_USERS, None)
            hass.data[DOMAIN].pop(CONF_CURRENCY, None)
        if not any(
            isinstance(value, dict) and "entry" in value
            for value in hass.data.get(DOMAIN, {}).values()
        ):
            hass.data.pop(DOMAIN, None)
    return unloaded
