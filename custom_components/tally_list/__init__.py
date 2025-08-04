"""Tally List integration."""

from __future__ import annotations

import csv
import os
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import Unauthorized
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
    PRICE_LIST_USER,
    CONF_CURRENCY,
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
        },
    )

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
        await _verify_permissions(call, user)
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
                    writer.writerow([state.name, f"{amount:.2f}"])

        def _cleanup(path: str, keep: int | None) -> None:
            if keep is None or keep <= 0:
                return
            cutoff = now - timedelta(days=keep)
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

        daily_cfg = {"enable": True, "keep_days": 7}
        daily_cfg.update(call.data.get("daily", {}))
        weekly_cfg = {"enable": True, "keep_days": 30}
        weekly_cfg.update(call.data.get("weekly", {}))
        monthly_cfg = {"enable": True, "interval": 3, "keep_days": 365}
        monthly_cfg.update(call.data.get("monthly", {}))
        manual_cfg = {"enable": True, "keep_days": 180}
        manual_cfg.update(call.data.get("manual", {}))

        if daily_cfg.get("enable"):
            file_path = os.path.join(
                base_dir, "daily", f"amount_due_{now.strftime('%Y-%m-%d_%H-%M')}.csv"
            )
            await hass.async_add_executor_job(_write_csv, file_path)
        await hass.async_add_executor_job(
            _cleanup, os.path.join(base_dir, "daily"), daily_cfg.get("keep_days")
        )

        if weekly_cfg.get("enable"):
            iso_year, iso_week, _ = now.isocalendar()
            weekly_file = os.path.join(
                base_dir,
                "weekly",
                f"amount_due_week_{iso_year}-{iso_week:02d}.csv",
            )
            if not os.path.exists(weekly_file):
                await hass.async_add_executor_job(_write_csv, weekly_file)
        await hass.async_add_executor_job(
            _cleanup, os.path.join(base_dir, "weekly"), weekly_cfg.get("keep_days")
        )

        if monthly_cfg.get("enable"):
            interval = monthly_cfg.get("interval", 1) or 1
            if now.month % interval == 0:
                monthly_file = os.path.join(
                    base_dir, "monthly", f"amount_due_{now.strftime('%Y-%m')}.csv"
                )
                if not os.path.exists(monthly_file):
                    await hass.async_add_executor_job(_write_csv, monthly_file)
        await hass.async_add_executor_job(
            _cleanup, os.path.join(base_dir, "monthly"), monthly_cfg.get("keep_days")
        )

        if manual_cfg.get("enable"):
            manual_file = os.path.join(
                base_dir,
                "manual",
                f"amount_due_manual_{now.strftime('%Y-%m-%d_%H-%M')}.csv",
            )
            await hass.async_add_executor_job(_write_csv, manual_file)
        await hass.async_add_executor_job(
            _cleanup, os.path.join(base_dir, "manual"), manual_cfg.get("keep_days")
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
    hass.data[DOMAIN].setdefault(
        entry.entry_id,
        {"entry": entry, "counts": {}},
    )
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
            hass.data[DOMAIN].pop(CONF_OVERRIDE_USERS, None)
            hass.data[DOMAIN].pop(CONF_CURRENCY, None)
        if not any(
            isinstance(value, dict) and "entry" in value
            for value in hass.data.get(DOMAIN, {}).values()
        ):
            hass.data.pop(DOMAIN, None)
    return unloaded
