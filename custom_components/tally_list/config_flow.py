"""Config flow for Tally List."""

from __future__ import annotations

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
    PRICE_LIST_USER,
)


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
        self._pending_users: list[str] = []

    async def async_step_import(self, user_input=None):
        """Handle import of a config entry."""
        if user_input is None:
            return self.async_abort(reason="invalid_import")
        self._user = user_input.get(CONF_USER)
        self._drinks = user_input.get(CONF_DRINKS, {})
        self._free_amount = float(user_input.get(CONF_FREE_AMOUNT, 0.0))
        self._excluded_users = user_input.get(CONF_EXCLUDED_USERS, [])
        return self.async_create_entry(title=self._user, data=user_input)

    async def async_step_user(self, user_input=None):
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

        excluded = set(
            self.hass.data.get(DOMAIN, {}).get(CONF_EXCLUDED_USERS, [])
        )

        persons = [
            p
            for p in persons
            if p not in existing and p not in excluded and p != PRICE_LIST_USER
        ]

        if not persons:
            return self.async_abort(reason="no_users")

        self._user = persons[0]
        self._pending_users = persons[1:]

        entries = self.hass.config_entries.async_entries(DOMAIN)
        has_price_user = any(
            entry.data.get(CONF_USER) == PRICE_LIST_USER for entry in entries
        )
        for entry in entries:
            if CONF_DRINKS in entry.data:
                self._drinks = entry.data[CONF_DRINKS]
                self._excluded_users = entry.data.get(CONF_EXCLUDED_USERS, [])
                if not has_price_user:
                    self.hass.async_create_task(
                        self.hass.config_entries.flow.async_init(
                            DOMAIN,
                            context={"source": config_entries.SOURCE_IMPORT},
                            data={
                                CONF_USER: PRICE_LIST_USER,
                                CONF_FREE_AMOUNT: 0.0,
                            },
                        )
                    )
                for p in self._pending_users:
                    self.hass.async_create_task(
                        self.hass.config_entries.flow.async_init(
                            DOMAIN,
                            context={"source": config_entries.SOURCE_IMPORT},
                            data={CONF_USER: p},
                        )
                    )
                self._pending_users = []
                return self.async_create_entry(
                    title=self._user,
                    data={CONF_USER: self._user},
                )

        return await self.async_step_add_drink()

    async def async_step_add_drink(self, user_input=None):
        if user_input is not None:
            drink = user_input[CONF_DRINK]
            price = float(user_input[CONF_PRICE])
            self._drinks[drink] = price
            if user_input.get("add_more"):
                return await self.async_step_add_drink()
            self.hass.data.setdefault(DOMAIN, {})["drinks"] = self._drinks

            has_price_user = any(
                entry.data.get(CONF_USER) == PRICE_LIST_USER
                for entry in self.hass.config_entries.async_entries(DOMAIN)
            )
            if not has_price_user:
                self.hass.async_create_task(
                    self.hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": config_entries.SOURCE_IMPORT},
                        data={
                            CONF_USER: PRICE_LIST_USER,
                            CONF_FREE_AMOUNT: 0.0,
                        },
                    )
                )
            for p in self._pending_users:
                self.hass.async_create_task(
                    self.hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": config_entries.SOURCE_IMPORT},
                        data={CONF_USER: p},
                    )
                )
            self._pending_users = []

            return self.async_create_entry(
                title=self._user,
                data={
                    CONF_USER: self._user,
                    CONF_DRINKS: self._drinks,
                    CONF_FREE_AMOUNT: 0.0,
                    CONF_EXCLUDED_USERS: self._excluded_users,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_DRINK): str,
                vol.Required(CONF_PRICE): vol.Coerce(float),
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="add_drink", data_schema=schema)

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

    async def async_step_init(self, user_input=None):
        self._drinks = (
            self.hass.data.get(DOMAIN, {})
            .get("drinks", {})
            .copy()
        )
        self._free_amount = self.hass.data.get(DOMAIN, {}).get(
            "free_amount", 0.0
        )
        self._excluded_users = (
            self.hass.data.get(DOMAIN, {}).get(CONF_EXCLUDED_USERS, [])
        ).copy()
        return await self.async_step_menu()

    async def async_step_menu(self, user_input=None):
        return self.async_show_menu(
            step_id="menu",
            menu_options=[
                "add",
                "remove",
                "edit",
                "free_amount",
                "exclude",
                "include",
                "finish",
            ],
        )

    async def async_step_add(self, user_input=None):
        return await self.async_step_add_drink(user_input)

    async def async_step_remove(self, user_input=None):
        return await self.async_step_remove_drink(user_input)

    async def async_step_edit(self, user_input=None):
        return await self.async_step_edit_price(user_input)

    async def async_step_free_amount(self, user_input=None):
        return await self.async_step_set_free_amount(user_input)

    async def async_step_exclude(self, user_input=None):
        return await self.async_step_add_excluded_user(user_input)

    async def async_step_include(self, user_input=None):
        return await self.async_step_remove_excluded_user(user_input)

    async def async_step_finish(self, user_input=None):
        if user_input is not None:
            return await self._update_drinks()
        return self.async_show_form(step_id="finish", last_step=True)

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
            if p not in self._excluded_users and p != PRICE_LIST_USER
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

    async def _update_drinks(self):
        # Update global drinks list before reloading entries so that new
        # sensors are created with the latest values during setup.
        self.hass.data.setdefault(DOMAIN, {})["drinks"] = self._drinks
        self.hass.data[DOMAIN]["free_amount"] = self._free_amount
        self.hass.data[DOMAIN][CONF_EXCLUDED_USERS] = self._excluded_users

        for entry in self.hass.config_entries.async_entries(DOMAIN):
            data = {
                CONF_USER: entry.data[CONF_USER],
                CONF_DRINKS: self._drinks,
                CONF_FREE_AMOUNT: self._free_amount,
                CONF_EXCLUDED_USERS: self._excluded_users,
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
            },
        )
