"""Config flow for Tally List."""

from __future__ import annotations

import logging
import os
import csv
import re
import voluptuous as vol

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import IconSelector
from homeassistant.util import dt as dt_util

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_USER,
    CONF_DRINKS,
    CONF_DRINK,
    CONF_PRICE,
    CONF_ICON,
    CONF_ICONS,
    CONF_FREE_AMOUNT,
    CONF_EXCLUDED_USERS,
    CONF_OVERRIDE_USERS,
    CONF_PUBLIC_DEVICES,
    PRICE_LIST_USERS,
    get_price_list_user,
    CONF_CURRENCY,
    CONF_ENABLE_FREE_DRINKS,
    CONF_CASH_USER_NAME,
    get_cash_user_name,
)

from .utils import get_person_name
from .sensor import PriceListFeedSensor


_LOGGER = logging.getLogger(__name__)


def _write_price_list_log(
    hass, user: str, action: str, details: str
) -> None:
    tz = dt_util.get_time_zone("Europe/Berlin")
    ts = dt_util.now(tz).replace(second=0, microsecond=0)
    base_dir = hass.config.path("tally_list", "price_list")
    os.makedirs(base_dir, exist_ok=True)
    path = os.path.join(base_dir, f"price_list_{ts.year}.csv")
    rows: list[list[str]] = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8", newline="") as csvfile:
            rows = list(csv.reader(csvfile, delimiter=";"))
    if not rows:
        rows = [["Time", "User", "Action", "Details"]]
    key_time = ts.strftime("%Y-%m-%dT%H:%M")
    if len(rows) > 1 and rows[-1][:3] == [key_time, user, action]:
        existing = rows[-1][3]
        prefix = f"{user}:"
        if existing.startswith(prefix) and details.startswith(prefix):
            existing_parts = existing[len(prefix):]
            new_parts = details[len(prefix):]
            counts: dict[tuple[str, str], int] = {}
            order: list[tuple[str, str]] = []

            def _parse(parts: str) -> bool:
                for part in parts.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    match = re.fullmatch(r"([^,+-]+)([+-])(\d+)", part)
                    if match is None:
                        return False
                    name, sign, num = match.groups()
                    key = (name, sign)
                    if key not in counts:
                        counts[key] = 0
                        order.append(key)
                    counts[key] += int(num)
                return True

            if _parse(existing_parts) and _parse(new_parts):
                rows[-1][3] = prefix + ",".join(
                    f"{name}{sign}{counts[(name, sign)]}" for name, sign in order
                )
            else:
                rows[-1][3] = f"{existing},{new_parts}"
        else:
            new_detail = (
                details[len(prefix):]
                if existing.startswith(prefix) and details.startswith(prefix)
                else details
            )
            rows[-1][3] = f"{existing},{new_detail}"
    else:
        rows.append([key_time, user, action, details])
    with open(path, "w", encoding="utf-8", newline="") as csvfile:
        writer = csv.writer(csvfile, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        writer.writerows(rows)


async def _async_update_price_feed_sensor(hass) -> None:
    sensor = hass.data[DOMAIN].get("price_list_feed_sensor")
    if sensor is not None:
        await sensor.async_update_state()
        return
    add_entities = hass.data[DOMAIN].get("price_feed_add_entities")
    feed_entry_id = hass.data[DOMAIN].get("price_feed_entry_id")
    entry = (
        hass.config_entries.async_get_entry(feed_entry_id)
        if feed_entry_id is not None
        else None
    )
    if add_entities is not None and entry is not None:
        sensor = PriceListFeedSensor(hass, entry)
        hass.data[DOMAIN]["price_list_feed_sensor"] = sensor
        add_entities([sensor])


async def _log_price_change(hass, user_id, action: str, details: str) -> None:
    auth = getattr(hass, "auth", None)
    if user_id is None and auth is not None:
        current = getattr(auth, "current_user", None)
        if current is not None:
            user_id = current.id
    hass_user = (
        await auth.async_get_user(user_id) if auth is not None and user_id else None
    )
    name = get_person_name(hass, user_id) or (
        hass_user.name if hass_user else "Unknown"
    )
    await hass.async_add_executor_job(
        _write_price_list_log, hass, name, action, details
    )
    await _async_update_price_feed_sensor(hass)


def _parse_drinks(value: str) -> dict[str, float]:
    drinks: dict[str, float] = {}
    if not value:
        return drinks
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            raise ValueError
        name, price = part.split("=", 1)
        drinks[name.strip()] = float(price)
    return drinks


class TallyListConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._user: str | None = None
        self._drinks: dict[str, float] = {}
        self._drink_icons: dict[str, str] = {}
        self._free_amount: float = 0.0
        self._excluded_users: list[str] = []
        self._override_users: list[str] = []
        self._public_devices: list[str] = []
        self._pending_users: list[str] = []
        self._currency: str = "€"
        self._create_price_user: bool = False
        self._user_selected: bool = False
        self._enable_free_drinks: bool = False
        self._cash_user_name: str = get_cash_user_name(None)
        self._edit_drink: str | None = None

    async def async_step_import(self, user_input=None):
        """Handle import of a config entry."""
        if user_input is None:
            return self.async_abort(reason="invalid_import")
        self._user = user_input.get(CONF_USER)
        self._drinks = user_input.get(CONF_DRINKS, {})
        self._drink_icons = user_input.get(CONF_ICONS, {})
        self._free_amount = float(user_input.get(CONF_FREE_AMOUNT, 0.0))
        self._excluded_users = user_input.get(CONF_EXCLUDED_USERS, [])
        self._override_users = user_input.get(CONF_OVERRIDE_USERS, [])
        self._public_devices = user_input.get(CONF_PUBLIC_DEVICES, [])
        self._currency = user_input.get(CONF_CURRENCY, "€")
        self._enable_free_drinks = user_input.get(CONF_ENABLE_FREE_DRINKS, False)
        self._cash_user_name = get_cash_user_name(
            getattr(self.hass.config, "language", None)
        )
        if CONF_CURRENCY not in user_input:
            user_input[CONF_CURRENCY] = self._currency
        if CONF_ENABLE_FREE_DRINKS not in user_input:
            user_input[CONF_ENABLE_FREE_DRINKS] = self._enable_free_drinks
        user_input[CONF_CASH_USER_NAME] = self._cash_user_name
        user_input[CONF_PUBLIC_DEVICES] = self._public_devices
        if CONF_ICONS not in user_input:
            user_input[CONF_ICONS] = self._drink_icons
        return self.async_create_entry(title=self._user, data=user_input)

    async def async_step_user(self, user_input=None):
        entries = self.hass.config_entries.async_entries(DOMAIN)
        if entries:
            registry = er.async_get(self.hass)
            persons = [
                entry.original_name or entry.name or entry.entity_id
                for entry in registry.entities.values()
                if entry.domain == "person"
                and (
                    (state := self.hass.states.get(entry.entity_id))
                    and state.attributes.get("user_id")
                )
            ]

            existing = {entry.data.get(CONF_USER) for entry in entries}

            excluded = set(self.hass.data.get(DOMAIN, {}).get(CONF_EXCLUDED_USERS, []))

            persons = [
                p
                for p in persons
                if p not in existing and p not in excluded and p not in PRICE_LIST_USERS
            ]

            if persons:
                data_template = {
                    CONF_DRINKS: self.hass.data.get(DOMAIN, {}).get(CONF_DRINKS, {}),
                    CONF_ICONS: self.hass.data.get(DOMAIN, {}).get(CONF_ICONS, {}),
                    CONF_FREE_AMOUNT: float(
                        self.hass.data.get(DOMAIN, {}).get(CONF_FREE_AMOUNT, 0.0)
                    ),
                    CONF_EXCLUDED_USERS: list(
                        self.hass.data.get(DOMAIN, {}).get(CONF_EXCLUDED_USERS, [])
                    ),
                    CONF_OVERRIDE_USERS: list(
                        self.hass.data.get(DOMAIN, {}).get(CONF_OVERRIDE_USERS, [])
                    ),
                    CONF_PUBLIC_DEVICES: list(
                        self.hass.data.get(DOMAIN, {}).get(CONF_PUBLIC_DEVICES, [])
                    ),
                    CONF_CURRENCY: self.hass.data.get(DOMAIN, {}).get(CONF_CURRENCY, "€"),
                    CONF_ENABLE_FREE_DRINKS: self.hass.data.get(DOMAIN, {}).get(
                        CONF_ENABLE_FREE_DRINKS, False
                    ),
                    CONF_CASH_USER_NAME: get_cash_user_name(
                        getattr(self.hass.config, "language", None)
                    ),
                }

                for person in persons:
                    data = {**data_template, CONF_USER: person}
                    self.hass.async_create_task(
                        self.hass.config_entries.flow.async_init(
                            DOMAIN,
                            context={"source": config_entries.SOURCE_IMPORT},
                            data=data,
                        )
                    )
            return self.async_abort(reason="already_configured")

        if not self._user_selected:
            self._cash_user_name = get_cash_user_name(
                getattr(self.hass.config, "language", None)
            )
            registry = er.async_get(self.hass)
            persons = [
                entry.original_name or entry.name or entry.entity_id
                for entry in registry.entities.values()
                if entry.domain == "person"
                and (
                    (state := self.hass.states.get(entry.entity_id))
                    and state.attributes.get("user_id")
                )
            ]

            existing = {entry.data.get(CONF_USER) for entry in entries}

            excluded = set(self.hass.data.get(DOMAIN, {}).get(CONF_EXCLUDED_USERS, []))
            # Preserve already excluded users when the price list user is recreated
            self._excluded_users = list(excluded)

            persons = [
                p
                for p in persons
                if p not in existing and p not in excluded and p not in PRICE_LIST_USERS
            ]

            self._create_price_user = not any(
                entry.data.get(CONF_USER) in PRICE_LIST_USERS for entry in entries
            )

            if not persons:
                return self.async_abort(reason="no_users")

            self._user = persons[0]
            self._pending_users = persons[1:]
            for entry in entries:
                if CONF_DRINKS in entry.data:
                    self._drinks = entry.data[CONF_DRINKS]
                    self._excluded_users = entry.data.get(CONF_EXCLUDED_USERS, [])
                    self._override_users = entry.data.get(CONF_OVERRIDE_USERS, [])
                    self._free_amount = float(entry.data.get(CONF_FREE_AMOUNT, 0.0))
                    self._currency = entry.data.get(CONF_CURRENCY, "€")
                    self._enable_free_drinks = entry.data.get(
                        CONF_ENABLE_FREE_DRINKS, False
                    )
                    self._cash_user_name = get_cash_user_name(
                        getattr(self.hass.config, "language", None)
                    )
                    break
            self._user_selected = True
            return await self.async_step_menu()

        return self.async_show_menu(
            step_id="user",
            menu_options=[
                "free_amount",
                "exclude",
                "include",
                "authorize",
                "unauthorize",
                "authorize_public",
                "unauthorize_public",
                "back",
            ],
        )

    async def async_step_menu(self, user_input=None):
        return self.async_show_menu(
            step_id="menu",
            menu_options=["user", "drinks", "finish"],
        )

    async def async_step_drinks(self, user_input=None):
        return self.async_show_menu(
            step_id="drinks",
            menu_options=["add", "remove", "edit", "currency", "back"],
        )

    async def async_step_back(self, user_input=None):
        return await self.async_step_menu()

    async def async_step_add(self, user_input=None):
        return await self.async_step_add_drink(user_input)

    async def async_step_remove(self, user_input=None):
        return await self.async_step_remove_drink(user_input)

    async def async_step_edit(self, user_input=None):
        return await self.async_step_edit_price(user_input)

    async def async_step_free_amount(self, user_input=None):
        return await self.async_step_set_free_amount(user_input)

    async def async_step_currency(self, user_input=None):
        if user_input is not None:
            self._currency = user_input[CONF_CURRENCY]
            return await self.async_step_menu()
        schema = vol.Schema({vol.Required(CONF_CURRENCY, default=self._currency): str})
        return self.async_show_form(step_id="currency", data_schema=schema)

    async def async_step_free_drinks(self, user_input=None):
        if user_input is not None:
            enable = user_input[CONF_ENABLE_FREE_DRINKS]
            if self._enable_free_drinks and not enable:
                return await self.async_step_free_drinks_confirm()
            self._enable_free_drinks = enable
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_FREE_DRINKS, default=self._enable_free_drinks
                ): bool
            }
        )
        return self.async_show_form(
            step_id="free_drinks", data_schema=schema
        )

    async def async_step_free_drinks_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            confirmation = user_input.get("confirm", "").strip().upper()
            if confirmation in {"JA ICH WILL", "YES I WANT"}:
                self._enable_free_drinks = False
                return await self.async_step_menu()
            errors["base"] = "confirmation_required"
        schema = vol.Schema({vol.Required("confirm"): str})
        return self.async_show_form(
            step_id="free_drinks_confirm", data_schema=schema, errors=errors
        )

    async def async_step_exclude(self, user_input=None):
        return await self.async_step_add_excluded_user(user_input)

    async def async_step_include(self, user_input=None):
        return await self.async_step_remove_excluded_user(user_input)

    async def async_step_authorize(self, user_input=None):
        return await self.async_step_add_override_user(user_input)

    async def async_step_unauthorize(self, user_input=None):
        return await self.async_step_remove_override_user(user_input)

    async def async_step_add_drink(self, user_input=None):
        if user_input is not None:
            drink = user_input[CONF_DRINK]
            price = float(user_input[CONF_PRICE])
            icon = user_input[CONF_ICON]
            self._drinks[drink] = price
            self._drink_icons[drink] = icon
            await _log_price_change(
                self.hass,
                self.context.get("user_id"),
                "add_drink",
                f"{drink}={price}",
            )
            if user_input.get("add_more"):
                return await self.async_step_add_drink()
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_DRINK): str,
                vol.Required(CONF_PRICE): vol.Coerce(float),
                vol.Required(CONF_ICON): IconSelector(),
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="add_drink", data_schema=schema)

    async def async_step_remove_drink(self, user_input=None):
        if user_input is not None:
            drink = user_input[CONF_DRINK]
            self._drinks.pop(drink, None)
            self._drink_icons.pop(drink, None)
            await _log_price_change(
                self.hass,
                self.context.get("user_id"),
                "remove_drink",
                drink,
            )
            if user_input.get("remove_more") and self._drinks:
                return await self.async_step_remove_drink()
            return await self.async_step_menu()
        if not self._drinks:
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_DRINK): vol.In(list(self._drinks.keys())),
                vol.Optional("remove_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="remove_drink", data_schema=schema)

    async def async_step_edit_price(self, user_input=None):
        if user_input is not None:
            if CONF_PRICE in user_input:
                drink = self._edit_drink
                price = float(user_input[CONF_PRICE])
                icon = user_input[CONF_ICON]
                old = self._drinks.get(drink)
                self._drinks[drink] = price
                self._drink_icons[drink] = icon
                await _log_price_change(
                    self.hass,
                    self.context.get("user_id"),
                    "edit_drink",
                    f"{drink}:{old}->{price}",
                )
                self._edit_drink = None
                if user_input.get("edit_more") and self._drinks:
                    return await self.async_step_edit_price()
                return await self.async_step_menu()
            self._edit_drink = user_input[CONF_DRINK]
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_PRICE, default=self._drinks[self._edit_drink]
                    ): vol.Coerce(float),
                    vol.Required(
                        CONF_ICON,
                        default=self._drink_icons.get(self._edit_drink),
                    ): IconSelector(),
                    vol.Optional("edit_more", default=False): bool,
                }
            )
            return self.async_show_form(step_id="edit_price", data_schema=schema)
        if not self._drinks:
            return await self.async_step_menu()
        schema = vol.Schema({vol.Required(CONF_DRINK): vol.In(list(self._drinks.keys()))})
        return self.async_show_form(step_id="edit_price", data_schema=schema)

    async def async_step_set_free_amount(self, user_input=None):
        if user_input is not None:
            old = self._free_amount
            self._free_amount = float(user_input[CONF_FREE_AMOUNT])
            await _log_price_change(
                self.hass,
                self.context.get("user_id"),
                "set_free_amount",
                f"{old}->{self._free_amount}",
            )
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_FREE_AMOUNT, default=self._free_amount): vol.Coerce(
                    float
                )
            }
        )
        return self.async_show_form(step_id="set_free_amount", data_schema=schema)

    async def async_step_add_excluded_user(self, user_input=None):
        registry = er.async_get(self.hass)
        persons = [
            entry.original_name or entry.name or entry.entity_id
            for entry in registry.entities.values()
            if entry.domain == "person"
            and (
                (state := self.hass.states.get(entry.entity_id))
                and state.attributes.get("user_id")
            )
        ]
        persons = [
            p
            for p in persons
            if p not in self._excluded_users and p not in PRICE_LIST_USERS
        ]
        if not persons:
            return await self.async_step_menu()
        if user_input is not None:
            user = user_input[CONF_USER]
            self._excluded_users.append(user)
            if user in self._pending_users:
                self._pending_users.remove(user)
            if user_input.get("add_more") and len(persons) > 1:
                return await self.async_step_add_excluded_user()
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(persons),
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="add_excluded_user", data_schema=schema)

    async def async_step_remove_excluded_user(self, user_input=None):
        if user_input is not None:
            user = user_input[CONF_USER]
            if user in self._excluded_users:
                self._excluded_users.remove(user)
                if user not in self._pending_users:
                    self._pending_users.append(user)
            if user_input.get("remove_more") and self._excluded_users:
                return await self.async_step_remove_excluded_user()
            return await self.async_step_menu()
        if not self._excluded_users:
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(list(self._excluded_users)),
                vol.Optional("remove_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="remove_excluded_user", data_schema=schema)

    async def async_step_add_override_user(self, user_input=None):
        registry = er.async_get(self.hass)
        persons = [
            entry.original_name or entry.name or entry.entity_id
            for entry in registry.entities.values()
            if entry.domain == "person"
            and (
                (state := self.hass.states.get(entry.entity_id))
                and state.attributes.get("user_id")
            )
        ]
        persons = [
            p
            for p in persons
            if p not in self._override_users and p not in PRICE_LIST_USERS
        ]
        if not persons:
            return await self.async_step_menu()
        if user_input is not None:
            user = user_input[CONF_USER]
            self._override_users.append(user)
            if user_input.get("add_more") and len(persons) > 1:
                return await self.async_step_add_override_user()
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(persons),
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="add_override_user", data_schema=schema)

    async def async_step_remove_override_user(self, user_input=None):
        if user_input is not None:
            user = user_input[CONF_USER]
            if user in self._override_users:
                self._override_users.remove(user)
            if user_input.get("remove_more") and self._override_users:
                return await self.async_step_remove_override_user()
            return await self.async_step_menu()
        if not self._override_users:
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(list(self._override_users)),
                vol.Optional("remove_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="remove_override_user", data_schema=schema)

    async def async_step_add_public_user(self, user_input=None):
        registry = er.async_get(self.hass)
        persons = [
            entry.original_name or entry.name or entry.entity_id
            for entry in registry.entities.values()
            if entry.domain == "person"
            and (
                (state := self.hass.states.get(entry.entity_id))
                and state.attributes.get("user_id")
            )
        ]
        persons = [
            p
            for p in persons
            if p not in self._public_devices and p not in PRICE_LIST_USERS
        ]
        if not persons:
            return await self.async_step_menu()
        if user_input is not None:
            user = user_input[CONF_USER]
            self._public_devices.append(user)
            if user_input.get("add_more") and len(persons) > 1:
                return await self.async_step_add_public_user()
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(persons),
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="add_public_user", data_schema=schema)

    async def async_step_remove_public_user(self, user_input=None):
        if user_input is not None:
            user = user_input[CONF_USER]
            if user in self._public_devices:
                self._public_devices.remove(user)
            if user_input.get("remove_more") and self._public_devices:
                return await self.async_step_remove_public_user()
            return await self.async_step_menu()
        if not self._public_devices:
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(list(self._public_devices)),
                vol.Optional("remove_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="remove_public_user", data_schema=schema)

    async def async_step_authorize_public(self, user_input=None):
        return await self.async_step_add_public_user(user_input)

    async def async_step_unauthorize_public(self, user_input=None):
        return await self.async_step_remove_public_user(user_input)

    async def async_step_finish(self, user_input=None):
        await self._finalize_setup()
        return self.async_create_entry(
            title=self._user,
            data={
                CONF_USER: self._user,
                CONF_DRINKS: self._drinks,
                CONF_ICONS: self._drink_icons,
                CONF_FREE_AMOUNT: self._free_amount,
                CONF_EXCLUDED_USERS: self._excluded_users,
                CONF_OVERRIDE_USERS: self._override_users,
                CONF_PUBLIC_DEVICES: self._public_devices,
                CONF_CURRENCY: self._currency,
                CONF_ENABLE_FREE_DRINKS: self._enable_free_drinks,
                CONF_CASH_USER_NAME: self._cash_user_name,
            },
        )

    async def _finalize_setup(self) -> None:
        self.hass.data.setdefault(DOMAIN, {})["drinks"] = self._drinks
        self.hass.data[DOMAIN]["drink_icons"] = self._drink_icons
        self.hass.data[DOMAIN]["free_amount"] = self._free_amount
        self.hass.data[DOMAIN][CONF_EXCLUDED_USERS] = self._excluded_users
        self.hass.data[DOMAIN][CONF_OVERRIDE_USERS] = self._override_users
        self.hass.data[DOMAIN][CONF_PUBLIC_DEVICES] = self._public_devices
        self.hass.data[DOMAIN][CONF_CURRENCY] = self._currency
        self.hass.data[DOMAIN][CONF_ENABLE_FREE_DRINKS] = self._enable_free_drinks
        self.hass.data[DOMAIN][CONF_CASH_USER_NAME] = self._cash_user_name
        if self._create_price_user:
            await self.hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data={
                    CONF_USER: get_price_list_user(
                        getattr(self.hass.config, "language", None)
                    ),
                    CONF_FREE_AMOUNT: self._free_amount,
                    CONF_DRINKS: self._drinks,
                    CONF_ICONS: self._drink_icons,
                    CONF_EXCLUDED_USERS: self._excluded_users,
                    CONF_OVERRIDE_USERS: self._override_users,
                    CONF_PUBLIC_DEVICES: self._public_devices,
                    CONF_CURRENCY: self._currency,
                },
            )
        else:
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if entry.data.get(CONF_USER) in PRICE_LIST_USERS:
                    entry_data = dict(entry.data)
                    entry_data[CONF_DRINKS] = self._drinks
                    entry_data[CONF_ICONS] = self._drink_icons
                    entry_data[CONF_FREE_AMOUNT] = self._free_amount
                    entry_data[CONF_EXCLUDED_USERS] = self._excluded_users
                    entry_data[CONF_OVERRIDE_USERS] = self._override_users
                    entry_data[CONF_PUBLIC_DEVICES] = self._public_devices
                    entry_data[CONF_CURRENCY] = self._currency
                    self.hass.config_entries.async_update_entry(entry, data=entry_data)
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    break
        for p in self._pending_users:
            if p in self._excluded_users:
                continue
            await self.hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": config_entries.SOURCE_IMPORT},
                data={CONF_USER: p},
            )
        self._pending_users = []
        cash_name = self._cash_user_name.strip()
        entries = self.hass.config_entries.async_entries(DOMAIN)
        cash_entry = next(
            (
                entry
                for entry in entries
                if entry.data.get(CONF_USER, "").strip().lower() == cash_name.lower()
            ),
            None,
        )
        if self._enable_free_drinks:
            if cash_entry is None:
                await self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": config_entries.SOURCE_IMPORT},
                    data={CONF_USER: cash_name},
                )
            else:
                cash_data = self.hass.data.get(DOMAIN, {}).get(cash_entry.entry_id)
                if cash_data is not None:
                    self.hass.data[DOMAIN]["free_drink_counts"] = cash_data.setdefault(
                        "counts", {}
                    )
        elif cash_entry is not None:
            cash_data = self.hass.data.get(DOMAIN, {}).get(cash_entry.entry_id)
            if cash_data is not None:
                cash_data["counts"] = {}
                for sensor in cash_data.get("sensors", []):
                    await sensor.async_update_state()
            await self.hass.config_entries.async_remove(cash_entry.entry_id)
            self.hass.data[DOMAIN].pop("free_drink_counts", None)
            self.hass.data[DOMAIN].pop("free_drinks_ledger", None)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TallyListOptionsFlowHandler(config_entry)


class TallyListOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        self.config_entry = config_entry
        self._drinks: dict[str, float] = {}
        self._drink_icons: dict[str, str] = {}
        self._free_amount: float = 0.0
        self._excluded_users: list[str] = []
        self._override_users: list[str] = []
        self._public_devices: list[str] = []
        self._currency: str = "€"
        self._enable_free_drinks: bool = False
        self._cash_user_name: str = get_cash_user_name(None)
        self._edit_drink: str | None = None

    async def async_step_init(self, user_input=None):
        self._drinks = self.hass.data.get(DOMAIN, {}).get("drinks", {}).copy()
        self._drink_icons = (
            self.hass.data.get(DOMAIN, {}).get("drink_icons", {})
        ).copy()
        self._free_amount = self.hass.data.get(DOMAIN, {}).get("free_amount", 0.0)
        self._excluded_users = (
            self.hass.data.get(DOMAIN, {}).get(CONF_EXCLUDED_USERS, [])
        ).copy()
        self._override_users = (
            self.hass.data.get(DOMAIN, {}).get(CONF_OVERRIDE_USERS, [])
        ).copy()
        self._public_devices = (
            self.hass.data.get(DOMAIN, {}).get(CONF_PUBLIC_DEVICES, [])
        ).copy()
        self._currency = self.hass.data.get(DOMAIN, {}).get(CONF_CURRENCY, "€")
        self._enable_free_drinks = self.hass.data.get(DOMAIN, {}).get(
            CONF_ENABLE_FREE_DRINKS, False
        )
        self._cash_user_name = get_cash_user_name(self.hass.config.language)
        return await self.async_step_menu()

    async def async_step_menu(self, user_input=None):
        return self.async_show_menu(
            step_id="menu",
            menu_options=[
                "user",
                "drinks",
                "cleanup",
                "delete",
                "finish",
            ],
        )

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(
            step_id="user",
            menu_options=[
                "free_amount",
                "exclude",
                "include",
                "authorize",
                "unauthorize",
                "authorize_public",
                "unauthorize_public",
                "back",
            ],
        )

    async def async_step_drinks(self, user_input=None):
        return self.async_show_menu(
            step_id="drinks",
            menu_options=[
                "add",
                "remove",
                "edit",
                "currency",
                "free_drinks",
                "back",
            ],
        )

    async def async_step_back(self, user_input=None):
        return await self.async_step_menu()

    async def async_step_add(self, user_input=None):
        return await self.async_step_add_drink(user_input)

    async def async_step_remove(self, user_input=None):
        return await self.async_step_remove_drink(user_input)

    async def async_step_edit(self, user_input=None):
        return await self.async_step_edit_price(user_input)

    async def async_step_free_amount(self, user_input=None):
        return await self.async_step_set_free_amount(user_input)

    async def async_step_currency(self, user_input=None):
        if user_input is not None:
            self._currency = user_input[CONF_CURRENCY]
            return await self.async_step_menu()
        schema = vol.Schema({vol.Required(CONF_CURRENCY, default=self._currency): str})
        return self.async_show_form(step_id="currency", data_schema=schema)

    async def async_step_free_drinks(self, user_input=None):
        if user_input is not None:
            enable = user_input[CONF_ENABLE_FREE_DRINKS]
            if self._enable_free_drinks and not enable:
                return await self.async_step_free_drinks_confirm()
            self._enable_free_drinks = enable
            return await self.async_step_drinks()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_FREE_DRINKS, default=self._enable_free_drinks
                ): bool
            }
        )
        return self.async_show_form(step_id="free_drinks", data_schema=schema)

    async def async_step_free_drinks_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            confirmation = user_input.get("confirm", "").strip().upper()
            if confirmation in {"JA ICH WILL", "YES I WANT"}:
                self._enable_free_drinks = False
                return self.async_show_menu(
                    step_id="menu",
                    menu_options=[
                        "user",
                        "drinks",
                        "cleanup",
                        "delete",
                        "finish",
                    ],
                )
            errors["base"] = "confirmation_required"
        schema = vol.Schema({vol.Required("confirm"): str})
        return self.async_show_form(
            step_id="free_drinks_confirm", data_schema=schema, errors=errors
        )

    async def async_step_exclude(self, user_input=None):
        return await self.async_step_add_excluded_user(user_input)

    async def async_step_include(self, user_input=None):
        return await self.async_step_remove_excluded_user(user_input)

    async def async_step_authorize(self, user_input=None):
        return await self.async_step_add_override_user(user_input)

    async def async_step_unauthorize(self, user_input=None):
        return await self.async_step_remove_override_user(user_input)

    async def async_step_cleanup(self, user_input=None):
        errors = {}
        if user_input is not None:
            confirmation = user_input.get("confirm", "").strip().upper()
            if confirmation in {"JA ICH WILL", "YES I WANT"}:
                removed = await self._cleanup_unused_entities()
                if removed:
                    return self.async_show_form(
                        step_id="cleanup_result",
                        description_placeholders={
                            "sensors": "\n- ".join(sorted(removed))
                        },
                    )
                return self.async_show_form(step_id="cleanup_result_empty")
            errors["base"] = "invalid_confirmation"
        schema = vol.Schema({vol.Required("confirm"): str})
        return self.async_show_form(
            step_id="cleanup", data_schema=schema, errors=errors
        )

    async def async_step_cleanup_result(self, user_input=None):
        return await self.async_step_menu()

    async def async_step_cleanup_result_empty(self, user_input=None):
        return await self.async_step_menu()

    async def async_step_delete(self, user_input=None):
        errors = {}
        if user_input is not None:
            confirmation = user_input.get("confirm", "").strip().upper()
            if confirmation in {"JA ICH WILL", "YES I WANT"}:
                await self._delete_all_entries()
                return self.async_abort(reason="delete_all")
            errors["base"] = "invalid_confirmation"
        schema = vol.Schema({vol.Required("confirm"): str})
        return self.async_show_form(
            step_id="delete", data_schema=schema, errors=errors
        )

    async def async_step_finish(self, user_input=None):
        return await self._update_drinks()

    async def async_step_add_drink(self, user_input=None):
        if user_input is not None:
            drink = user_input[CONF_DRINK]
            price = float(user_input[CONF_PRICE])
            icon = user_input[CONF_ICON]
            self._drinks[drink] = price
            self._drink_icons[drink] = icon
            await _log_price_change(
                self.hass,
                self.context.get("user_id"),
                "add_drink",
                f"{drink}={price}",
            )
            if user_input.get("add_more"):
                return await self.async_step_add_drink()
            return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_DRINK): str,
                vol.Required(CONF_PRICE): vol.Coerce(float),
                vol.Required(CONF_ICON): IconSelector(),
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="add_drink", data_schema=schema)

    async def async_step_remove_drink(self, user_input=None):
        if user_input is not None:
            drink = user_input[CONF_DRINK]
            self._drinks.pop(drink, None)
            self._drink_icons.pop(drink, None)
            await _log_price_change(
                self.hass,
                self.context.get("user_id"),
                "remove_drink",
                drink,
            )
            if user_input.get("remove_more") and self._drinks:
                return await self.async_step_remove_drink()
            return await self.async_step_menu()

        if not self._drinks:
            return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_DRINK): vol.In(list(self._drinks.keys())),
                vol.Optional("remove_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="remove_drink", data_schema=schema)

    async def async_step_edit_price(self, user_input=None):
        if user_input is not None:
            if CONF_PRICE in user_input:
                drink = self._edit_drink
                price = float(user_input[CONF_PRICE])
                icon = user_input[CONF_ICON]
                old = self._drinks.get(drink)
                self._drinks[drink] = price
                self._drink_icons[drink] = icon
                await _log_price_change(
                    self.hass,
                    self.context.get("user_id"),
                    "edit_drink",
                    f"{drink}:{old}->{price}",
                )
                self._edit_drink = None
                if user_input.get("edit_more") and self._drinks:
                    return await self.async_step_edit_price()
                return await self.async_step_menu()
            self._edit_drink = user_input[CONF_DRINK]
            schema = vol.Schema(
                {
                    vol.Required(
                        CONF_PRICE, default=self._drinks[self._edit_drink]
                    ): vol.Coerce(float),
                    vol.Required(
                        CONF_ICON,
                        default=self._drink_icons.get(self._edit_drink),
                    ): IconSelector(),
                    vol.Optional("edit_more", default=False): bool,
                }
            )
            return self.async_show_form(step_id="edit_price", data_schema=schema)

        if not self._drinks:
            return await self.async_step_menu()

        schema = vol.Schema({vol.Required(CONF_DRINK): vol.In(list(self._drinks.keys()))})
        return self.async_show_form(step_id="edit_price", data_schema=schema)

    async def async_step_set_free_amount(self, user_input=None):
        if user_input is not None:
            old = self._free_amount
            self._free_amount = float(user_input[CONF_FREE_AMOUNT])
            await _log_price_change(
                self.hass,
                self.context.get("user_id"),
                "set_free_amount",
                f"{old}->{self._free_amount}",
            )
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_FREE_AMOUNT,
                    default=self._free_amount,
                ): vol.Coerce(float)
            }
        )
        return self.async_show_form(
            step_id="set_free_amount",
            data_schema=schema,
        )

    async def async_step_add_excluded_user(self, user_input=None):
        registry = er.async_get(self.hass)
        persons = [
            entry.original_name or entry.name or entry.entity_id
            for entry in registry.entities.values()
            if entry.domain == "person"
            and (
                (state := self.hass.states.get(entry.entity_id))
                and state.attributes.get("user_id")
            )
        ]
        persons = [
            p
            for p in persons
            if p not in self._excluded_users and p not in PRICE_LIST_USERS
        ]

        if not persons:
            return await self.async_step_menu()

        if user_input is not None:
            user = user_input[CONF_USER]
            self._excluded_users.append(user)
            if user_input.get("add_more") and len(persons) > 1:
                return await self.async_step_add_excluded_user()
            return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(persons),
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="add_excluded_user",
            data_schema=schema,
        )

    async def async_step_remove_excluded_user(self, user_input=None):
        if user_input is not None:
            user = user_input[CONF_USER]
            if user in self._excluded_users:
                self._excluded_users.remove(user)
            if user_input.get("remove_more") and self._excluded_users:
                return await self.async_step_remove_excluded_user()
            return await self.async_step_menu()

        if not self._excluded_users:
            return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(list(self._excluded_users)),
                vol.Optional("remove_more", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="remove_excluded_user",
            data_schema=schema,
        )

    async def async_step_add_override_user(self, user_input=None):
        registry = er.async_get(self.hass)
        persons = [
            entry.original_name or entry.name or entry.entity_id
            for entry in registry.entities.values()
            if entry.domain == "person"
            and (
                (state := self.hass.states.get(entry.entity_id))
                and state.attributes.get("user_id")
            )
        ]
        persons = [
            p
            for p in persons
            if p not in self._override_users and p not in PRICE_LIST_USERS
        ]

        if not persons:
            return await self.async_step_menu()

        if user_input is not None:
            user = user_input[CONF_USER]
            self._override_users.append(user)
            if user_input.get("add_more") and len(persons) > 1:
                return await self.async_step_add_override_user()
            return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(persons),
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="add_override_user",
            data_schema=schema,
        )

    async def async_step_remove_override_user(self, user_input=None):
        if user_input is not None:
            user = user_input[CONF_USER]
            if user in self._override_users:
                self._override_users.remove(user)
            if user_input.get("remove_more") and self._override_users:
                return await self.async_step_remove_override_user()
            return await self.async_step_menu()

        if not self._override_users:
            return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(list(self._override_users)),
                vol.Optional("remove_more", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="remove_override_user",
            data_schema=schema,
        )

    async def async_step_add_public_user(self, user_input=None):
        registry = er.async_get(self.hass)
        persons = [
            entry.original_name or entry.name or entry.entity_id
            for entry in registry.entities.values()
            if entry.domain == "person"
            and (
                (state := self.hass.states.get(entry.entity_id))
                and state.attributes.get("user_id")
            )
        ]
        persons = [
            p
            for p in persons
            if p not in self._public_devices and p not in PRICE_LIST_USERS
        ]
        if not persons:
            return await self.async_step_menu()
        if user_input is not None:
            user = user_input[CONF_USER]
            self._public_devices.append(user)
            if user_input.get("add_more") and len(persons) > 1:
                return await self.async_step_add_public_user()
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(persons),
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="add_public_user", data_schema=schema)

    async def async_step_remove_public_user(self, user_input=None):
        if user_input is not None:
            user = user_input[CONF_USER]
            if user in self._public_devices:
                self._public_devices.remove(user)
            if user_input.get("remove_more") and self._public_devices:
                return await self.async_step_remove_public_user()
            return await self.async_step_menu()
        if not self._public_devices:
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(list(self._public_devices)),
                vol.Optional("remove_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="remove_public_user", data_schema=schema)

    async def async_step_authorize_public(self, user_input=None):
        return await self.async_step_add_public_user(user_input)

    async def async_step_unauthorize_public(self, user_input=None):
        return await self.async_step_remove_public_user(user_input)

    async def _cleanup_unused_entities(self) -> list[str]:
        registry = er.async_get(self.hass)
        entries = self.hass.config_entries.async_entries(DOMAIN)
        entry_ids = {entry.entry_id for entry in entries}
        active_users = {entry.data.get(CONF_USER) for entry in entries}
        active_drinks = set(self._drinks.keys())

        to_remove: list[str] = []

        for entity_entry in list(registry.entities.values()):
            if entity_entry.domain != "sensor" or entity_entry.platform != DOMAIN:
                continue

            if entity_entry.config_entry_id not in entry_ids:
                to_remove.append(entity_entry.entity_id)
                continue

            cfg_entry = next(
                (e for e in entries if e.entry_id == entity_entry.config_entry_id),
                None,
            )

            if not cfg_entry:
                to_remove.append(entity_entry.entity_id)
                continue

            user = cfg_entry.data.get(CONF_USER)
            if user not in active_users:
                to_remove.append(entity_entry.entity_id)
                continue

            uid = entity_entry.unique_id or ""
            prefix = f"{cfg_entry.entry_id}_"
            if not uid.startswith(prefix):
                continue

            if uid.endswith("_count"):
                drink = uid[len(prefix) : -6]
            elif uid.endswith("_price"):
                drink = uid[len(prefix) : -6]
            elif uid.endswith("_free_amount"):
                drink = None
            elif uid.endswith("_amount_due") or uid.endswith("_reset_tally"):
                drink = None
            else:
                continue

            if drink is not None and drink not in active_drinks:
                to_remove.append(entity_entry.entity_id)

        if to_remove:
            for entity_id in to_remove:
                try:
                    await registry.async_remove(entity_id)
                except Exception as exc:  # pragma: no cover - just log
                    _LOGGER.error("Failed to remove %s: %s", entity_id, exc)

            for entry in entries:
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(entry.entry_id)
                )

            return sorted(to_remove)
        return []

    async def _delete_all_entries(self) -> None:
        entries = list(self.hass.config_entries.async_entries(DOMAIN))
        for entry in entries:
            await self.hass.config_entries.async_remove(entry.entry_id)

        registry = er.async_get(self.hass)
        for entity_entry in list(registry.entities.values()):
            if entity_entry.domain == "sensor" and entity_entry.platform == DOMAIN:
                try:
                    await registry.async_remove(entity_entry.entity_id)
                except Exception as exc:  # pragma: no cover - just log
                    _LOGGER.error("Failed to remove %s: %s", entity_entry.entity_id, exc)

        self.hass.data.pop(DOMAIN, None)

    async def _update_drinks(self):
        # Update global drinks list before reloading entries so that new
        # sensors are created with the latest values during setup.
        self.hass.data.setdefault(DOMAIN, {})["drinks"] = self._drinks
        self.hass.data[DOMAIN]["drink_icons"] = self._drink_icons
        self.hass.data[DOMAIN]["free_amount"] = self._free_amount
        self.hass.data[DOMAIN][CONF_EXCLUDED_USERS] = self._excluded_users
        self.hass.data[DOMAIN][CONF_OVERRIDE_USERS] = self._override_users
        self.hass.data[DOMAIN][CONF_PUBLIC_DEVICES] = self._public_devices
        self.hass.data[DOMAIN][CONF_CURRENCY] = self._currency
        self.hass.data[DOMAIN][CONF_CASH_USER_NAME] = self._cash_user_name
        cash_name = self._cash_user_name.strip()
        entries = self.hass.config_entries.async_entries(DOMAIN)
        cash_entry = next(
            (
                e
                for e in entries
                if e.data.get(CONF_USER, "").strip().lower() == cash_name.lower()
            ),
            None,
        )
        if self._enable_free_drinks:
            if cash_entry is None:
                self.hass.async_create_task(
                    self.hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": config_entries.SOURCE_IMPORT},
                        data={CONF_USER: cash_name},
                    )
                )
            else:
                cash_data = self.hass.data.get(DOMAIN, {}).get(cash_entry.entry_id)
                if cash_data is not None:
                    self.hass.data[DOMAIN]["free_drink_counts"] = cash_data.setdefault(
                        "counts", {}
                    )
        elif cash_entry is not None:
            cash_data = self.hass.data.get(DOMAIN, {}).get(cash_entry.entry_id)
            if cash_data is not None:
                cash_data["counts"] = {}
                for sensor in cash_data.get("sensors", []):
                    await sensor.async_update_state()
            self.hass.async_create_task(
                self.hass.config_entries.async_remove(cash_entry.entry_id)
            )
            self.hass.data[DOMAIN].pop("free_drink_counts", None)
            self.hass.data[DOMAIN].pop("free_drinks_ledger", None)
            self.hass.data[DOMAIN].pop(cash_entry.entry_id, None)
            entries = [e for e in entries if e.entry_id != cash_entry.entry_id]

        for entry in entries:
            data = {
                CONF_USER: entry.data[CONF_USER],
                CONF_DRINKS: self._drinks,
                CONF_ICONS: self._drink_icons,
                CONF_FREE_AMOUNT: self._free_amount,
                CONF_EXCLUDED_USERS: self._excluded_users,
                CONF_OVERRIDE_USERS: self._override_users,
                CONF_PUBLIC_DEVICES: self._public_devices,
                CONF_CURRENCY: self._currency,
                CONF_ENABLE_FREE_DRINKS: self._enable_free_drinks,
                CONF_CASH_USER_NAME: self._cash_user_name,
            }
            self.hass.config_entries.async_update_entry(entry, data=data)
            await self.hass.config_entries.async_reload(entry.entry_id)
        for entry in entries:
            value = self.hass.data.get(DOMAIN, {}).get(entry.entry_id)
            if isinstance(value, dict):
                for sensor in value.get("sensors", []):
                    await sensor.async_update_state()
        return self.async_create_entry(
            title="",
            data={
                CONF_DRINKS: self._drinks,
                CONF_ICONS: self._drink_icons,
                CONF_FREE_AMOUNT: self._free_amount,
                CONF_EXCLUDED_USERS: self._excluded_users,
                CONF_OVERRIDE_USERS: self._override_users,
                CONF_PUBLIC_DEVICES: self._public_devices,
                CONF_CURRENCY: self._currency,
                CONF_ENABLE_FREE_DRINKS: self._enable_free_drinks,
                CONF_CASH_USER_NAME: self._cash_user_name,
            },
        )
