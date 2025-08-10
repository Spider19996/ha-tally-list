"""Config flow for Tally List."""

from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant.helpers import entity_registry as er

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_USER,
    CONF_DRINKS,
    CONF_DRINK,
    CONF_PRICE,
    CONF_FREE_AMOUNT,
    CONF_EXCLUDED_USERS,
    CONF_OVERRIDE_USERS,
    PRICE_LIST_USERS,
    get_price_list_user,
    CONF_CURRENCY,
    CONF_ENABLE_FREE_MARKS,
    CONF_CASH_USER_NAME,
    get_cash_user_name,
)


_LOGGER = logging.getLogger(__name__)


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
        self._free_amount: float = 0.0
        self._excluded_users: list[str] = []
        self._override_users: list[str] = []
        self._pending_users: list[str] = []
        self._currency: str = "€"
        self._create_price_user: bool = False
        self._user_selected: bool = False
        self._enable_free_marks: bool = False
        self._cash_user_name: str = get_cash_user_name(None)

    async def async_step_import(self, user_input=None):
        """Handle import of a config entry."""
        if user_input is None:
            return self.async_abort(reason="invalid_import")
        self._user = user_input.get(CONF_USER)
        self._drinks = user_input.get(CONF_DRINKS, {})
        self._free_amount = float(user_input.get(CONF_FREE_AMOUNT, 0.0))
        self._excluded_users = user_input.get(CONF_EXCLUDED_USERS, [])
        self._override_users = user_input.get(CONF_OVERRIDE_USERS, [])
        self._currency = user_input.get(CONF_CURRENCY, "€")
        self._enable_free_marks = user_input.get(CONF_ENABLE_FREE_MARKS, False)
        self._cash_user_name = user_input.get(
            CONF_CASH_USER_NAME,
            get_cash_user_name(getattr(self.hass.config, "language", None)),
        )
        if CONF_CURRENCY not in user_input:
            user_input[CONF_CURRENCY] = self._currency
        if CONF_ENABLE_FREE_MARKS not in user_input:
            user_input[CONF_ENABLE_FREE_MARKS] = self._enable_free_marks
        if CONF_CASH_USER_NAME not in user_input:
            user_input[CONF_CASH_USER_NAME] = self._cash_user_name
        return self.async_create_entry(title=self._user, data=user_input)

    async def async_step_user(self, user_input=None):
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

            existing = {
                entry.data.get(CONF_USER)
                for entry in self.hass.config_entries.async_entries(DOMAIN)
            }

            excluded = set(self.hass.data.get(DOMAIN, {}).get(CONF_EXCLUDED_USERS, []))
            # Preserve already excluded users when the price list user is recreated
            self._excluded_users = list(excluded)

            persons = [
                p
                for p in persons
                if p not in existing and p not in excluded and p not in PRICE_LIST_USERS
            ]

            entries = self.hass.config_entries.async_entries(DOMAIN)
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
                    self._enable_free_marks = entry.data.get(
                        CONF_ENABLE_FREE_MARKS, False
                    )
                    self._cash_user_name = entry.data.get(
                        CONF_CASH_USER_NAME,
                        get_cash_user_name(getattr(self.hass.config, "language", None)),
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

    async def async_step_free_marks(self, user_input=None):
        if user_input is not None:
            enable = user_input[CONF_ENABLE_FREE_MARKS]
            name = user_input.get(CONF_CASH_USER_NAME, self._cash_user_name)
            name = name.strip()
            if self._enable_free_marks and not enable:
                self._cash_user_name = name
                return await self.async_step_free_marks_confirm()
            self._enable_free_marks = enable
            self._cash_user_name = name
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_FREE_MARKS, default=self._enable_free_marks
                ): bool,
                vol.Optional(
                    CONF_CASH_USER_NAME, default=self._cash_user_name
                ): str,
            }
        )
        return self.async_show_form(
            step_id="free_marks",
            data_schema=schema,
        )

    async def async_step_free_marks_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            confirmation = user_input.get("confirm", "").strip().upper()
            if confirmation in {"JA ICH WILL", "YES I WANT"}:
                self._enable_free_marks = False
                return await self.async_step_menu()
            errors["base"] = "confirmation_required"
        schema = vol.Schema({vol.Required("confirm"): str})
        return self.async_show_form(
            step_id="free_marks_confirm", data_schema=schema, errors=errors
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
            self._drinks[drink] = price
            if user_input.get("add_more"):
                return await self.async_step_add_drink()
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_DRINK): str,
                vol.Required(CONF_PRICE): vol.Coerce(float),
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="add_drink", data_schema=schema)

    async def async_step_remove_drink(self, user_input=None):
        if user_input is not None:
            drink = user_input[CONF_DRINK]
            self._drinks.pop(drink, None)
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
            drink = user_input[CONF_DRINK]
            price = float(user_input[CONF_PRICE])
            self._drinks[drink] = price
            if user_input.get("edit_more") and self._drinks:
                return await self.async_step_edit_price()
            return await self.async_step_menu()
        if not self._drinks:
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_DRINK): vol.In(list(self._drinks.keys())),
                vol.Required(CONF_PRICE): vol.Coerce(float),
                vol.Optional("edit_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="edit_price", data_schema=schema)

    async def async_step_set_free_amount(self, user_input=None):
        if user_input is not None:
            self._free_amount = float(user_input[CONF_FREE_AMOUNT])
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

    async def async_step_finish(self, user_input=None):
        await self._finalize_setup()
        return self.async_create_entry(
            title=self._user,
            data={
                CONF_USER: self._user,
                CONF_DRINKS: self._drinks,
                CONF_FREE_AMOUNT: self._free_amount,
                CONF_EXCLUDED_USERS: self._excluded_users,
                CONF_OVERRIDE_USERS: self._override_users,
                CONF_CURRENCY: self._currency,
                CONF_ENABLE_FREE_MARKS: self._enable_free_marks,
                CONF_CASH_USER_NAME: self._cash_user_name,
            },
        )

    async def _finalize_setup(self) -> None:
        self.hass.data.setdefault(DOMAIN, {})["drinks"] = self._drinks
        self.hass.data[DOMAIN]["free_amount"] = self._free_amount
        self.hass.data[DOMAIN][CONF_EXCLUDED_USERS] = self._excluded_users
        self.hass.data[DOMAIN][CONF_OVERRIDE_USERS] = self._override_users
        self.hass.data[DOMAIN][CONF_CURRENCY] = self._currency
        self.hass.data[DOMAIN][CONF_ENABLE_FREE_MARKS] = self._enable_free_marks
        self.hass.data[DOMAIN][CONF_CASH_USER_NAME] = self._cash_user_name
        if self._create_price_user:
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": config_entries.SOURCE_IMPORT},
                    data={
                        CONF_USER: get_price_list_user(
                            getattr(self.hass.config, "language", None)
                        ),
                        CONF_FREE_AMOUNT: self._free_amount,
                        CONF_DRINKS: self._drinks,
                        CONF_EXCLUDED_USERS: self._excluded_users,
                        CONF_OVERRIDE_USERS: self._override_users,
                        CONF_CURRENCY: self._currency,
                    },
                )
            )
        else:
            for entry in self.hass.config_entries.async_entries(DOMAIN):
                if entry.data.get(CONF_USER) in PRICE_LIST_USERS:
                    entry_data = dict(entry.data)
                    entry_data[CONF_DRINKS] = self._drinks
                    entry_data[CONF_FREE_AMOUNT] = self._free_amount
                    entry_data[CONF_EXCLUDED_USERS] = self._excluded_users
                    entry_data[CONF_OVERRIDE_USERS] = self._override_users
                    entry_data[CONF_CURRENCY] = self._currency
                    self.hass.config_entries.async_update_entry(entry, data=entry_data)
                    await self.hass.config_entries.async_reload(entry.entry_id)
                    break
        for p in self._pending_users:
            if p in self._excluded_users:
                continue
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": config_entries.SOURCE_IMPORT},
                    data={CONF_USER: p},
                )
            )
        self._pending_users = []
        if self._enable_free_marks:
            cash_name = self._cash_user_name.strip()
            entries = self.hass.config_entries.async_entries(DOMAIN)
            cash_entry = next(
                (
                    entry
                    for entry in entries
                    if entry.data.get(CONF_USER, "").strip().lower()
                    == cash_name.lower()
                ),
                None,
            )
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
                    self.hass.data[DOMAIN]["free_mark_counts"] = cash_data.setdefault(
                        "counts", {}
                    )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TallyListOptionsFlowHandler(config_entry)


class TallyListOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        self.config_entry = config_entry
        self._drinks: dict[str, float] = {}
        self._free_amount: float = 0.0
        self._excluded_users: list[str] = []
        self._override_users: list[str] = []
        self._currency: str = "€"
        self._enable_free_marks: bool = False
        self._cash_user_name: str = get_cash_user_name(None)

    async def async_step_init(self, user_input=None):
        self._drinks = self.hass.data.get(DOMAIN, {}).get("drinks", {}).copy()
        self._free_amount = self.hass.data.get(DOMAIN, {}).get("free_amount", 0.0)
        self._excluded_users = (
            self.hass.data.get(DOMAIN, {}).get(CONF_EXCLUDED_USERS, [])
        ).copy()
        self._override_users = (
            self.hass.data.get(DOMAIN, {}).get(CONF_OVERRIDE_USERS, [])
        ).copy()
        self._currency = self.hass.data.get(DOMAIN, {}).get(CONF_CURRENCY, "€")
        self._enable_free_marks = self.hass.data.get(DOMAIN, {}).get(
            CONF_ENABLE_FREE_MARKS, False
        )
        self._cash_user_name = self.hass.data.get(DOMAIN, {}).get(
            CONF_CASH_USER_NAME, get_cash_user_name(self.hass.config.language)
        )
        return await self.async_step_menu()

    async def async_step_menu(self, user_input=None):
        return self.async_show_menu(
            step_id="menu",
            menu_options=[
                "user",
                "drinks",
                "free_marks",
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

    async def async_step_free_marks(self, user_input=None):
        if user_input is not None:
            enable = user_input[CONF_ENABLE_FREE_MARKS]
            name = user_input.get(CONF_CASH_USER_NAME, self._cash_user_name)
            name = name.strip()
            if self._enable_free_marks and not enable:
                self._cash_user_name = name
                return await self.async_step_free_marks_confirm()
            self._enable_free_marks = enable
            self._cash_user_name = name
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ENABLE_FREE_MARKS, default=self._enable_free_marks
                ): bool,
                vol.Optional(
                    CONF_CASH_USER_NAME, default=self._cash_user_name
                ): str,
            }
        )
        return self.async_show_form(step_id="free_marks", data_schema=schema)

    async def async_step_free_marks_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            confirmation = user_input.get("confirm", "").strip().upper()
            if confirmation in {"JA ICH WILL", "YES I WANT"}:
                self._enable_free_marks = False
                return await self.async_step_menu()
            errors["base"] = "confirmation_required"
        schema = vol.Schema({vol.Required("confirm"): str})
        return self.async_show_form(
            step_id="free_marks_confirm", data_schema=schema, errors=errors
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
            self._drinks[drink] = price
            if user_input.get("add_more"):
                return await self.async_step_add_drink()
            return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_DRINK): str,
                vol.Required(CONF_PRICE): vol.Coerce(float),
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="add_drink", data_schema=schema)

    async def async_step_remove_drink(self, user_input=None):
        if user_input is not None:
            drink = user_input[CONF_DRINK]
            self._drinks.pop(drink, None)
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
            drink = user_input[CONF_DRINK]
            price = float(user_input[CONF_PRICE])
            self._drinks[drink] = price
            if user_input.get("edit_more") and self._drinks:
                return await self.async_step_edit_price()
            return await self.async_step_menu()

        if not self._drinks:
            return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_DRINK): vol.In(list(self._drinks.keys())),
                vol.Required(CONF_PRICE): vol.Coerce(float),
                vol.Optional("edit_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="edit_price", data_schema=schema)

    async def async_step_set_free_amount(self, user_input=None):
        if user_input is not None:
            self._free_amount = float(user_input[CONF_FREE_AMOUNT])
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
        self.hass.data[DOMAIN]["free_amount"] = self._free_amount
        self.hass.data[DOMAIN][CONF_EXCLUDED_USERS] = self._excluded_users
        self.hass.data[DOMAIN][CONF_OVERRIDE_USERS] = self._override_users
        self.hass.data[DOMAIN][CONF_CURRENCY] = self._currency
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
        if self._enable_free_marks:
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
                    self.hass.data[DOMAIN]["free_mark_counts"] = cash_data.setdefault(
                        "counts", {}
                    )
        elif cash_entry is not None:
            cash_data = self.hass.data.get(DOMAIN, {}).get(cash_entry.entry_id)
            if cash_data is not None:
                cash_data["counts"] = {}
                for sensor in cash_data.get("sensors", []):
                    await sensor.async_update_state()
            await self.hass.config_entries.async_remove(cash_entry.entry_id)
            self.hass.data[DOMAIN].pop("free_mark_counts", None)

        for entry in self.hass.config_entries.async_entries(DOMAIN):
            data = {
                CONF_USER: entry.data[CONF_USER],
                CONF_DRINKS: self._drinks,
                CONF_FREE_AMOUNT: self._free_amount,
                CONF_EXCLUDED_USERS: self._excluded_users,
                CONF_OVERRIDE_USERS: self._override_users,
                CONF_CURRENCY: self._currency,
                CONF_ENABLE_FREE_MARKS: self._enable_free_marks,
                CONF_CASH_USER_NAME: self._cash_user_name,
            }
            self.hass.config_entries.async_update_entry(entry, data=data)
            await self.hass.config_entries.async_reload(entry.entry_id)
        for value in self.hass.data.get(DOMAIN, {}).values():
            if isinstance(value, dict):
                for sensor in value.get("sensors", []):
                    await sensor.async_update_state()
        return self.async_create_entry(
            title="",
            data={
                CONF_DRINKS: self._drinks,
                CONF_FREE_AMOUNT: self._free_amount,
                CONF_EXCLUDED_USERS: self._excluded_users,
                CONF_OVERRIDE_USERS: self._override_users,
                CONF_CURRENCY: self._currency,
                CONF_ENABLE_FREE_MARKS: self._enable_free_marks,
                CONF_CASH_USER_NAME: self._cash_user_name,
            },
        )
