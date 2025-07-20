"""Config flow for Drink Counter."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_USER,
    CONF_USERS,
    CONF_DRINKS,
    CONF_DRINK,
    CONF_PRICE,
    CONF_FREE_AMOUNT,
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


class DrinkCounterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 2

    def __init__(self) -> None:
        self._user: str | None = None
        self._drinks: dict[str, float] = {}
        self._free_amount: float = 0.0

    async def async_step_import(self, user_input=None):
        """Handle import of a config entry."""
        if user_input is None:
            return self.async_abort(reason="invalid_import")
        self._user = user_input.get(CONF_USER)
        self._drinks = user_input.get(CONF_DRINKS, {})
        self._free_amount = float(user_input.get(CONF_FREE_AMOUNT, 0.0))
        return self.async_create_entry(
            title="Drink Counter",
            data={
                CONF_USERS: [self._user, PRICE_LIST_USER],
                CONF_DRINKS: self._drinks,
                CONF_FREE_AMOUNT: self._free_amount,
            },
        )

    async def async_step_user(self, user_input=None):
        entries = self.hass.config_entries.async_entries(DOMAIN)
        if entries:
            entry = entries[0]
            if user_input is not None:
                self._user = user_input[CONF_USER]
                users = list(entry.data.get(CONF_USERS, []))
                if self._user in users:
                    return self.async_abort(reason="user_exists")
                users.append(self._user)
                data = {
                    CONF_USERS: users,
                    CONF_DRINKS: entry.data.get(CONF_DRINKS, {}),
                    CONF_FREE_AMOUNT: entry.data.get(CONF_FREE_AMOUNT, 0.0),
                }
                self.hass.config_entries.async_update_entry(entry, data=data)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_create_entry(title="", data={})
            schema = vol.Schema({vol.Required(CONF_USER): str})
            return self.async_show_form(step_id="user", data_schema=schema)

        if user_input is not None:
            self._user = user_input[CONF_USER]
            return await self.async_step_add_drink()

        schema = vol.Schema({vol.Required(CONF_USER): str})
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_add_drink(self, user_input=None):
        if user_input is not None:
            drink = user_input[CONF_DRINK]
            price = float(user_input[CONF_PRICE])
            self._drinks[drink] = price
            if user_input.get("add_more"):
                return await self.async_step_add_drink()
            self.hass.data.setdefault(DOMAIN, {})["drinks"] = self._drinks
            return self.async_create_entry(
                title="Drink Counter",
                data={
                    CONF_USERS: [self._user, PRICE_LIST_USER],
                    CONF_DRINKS: self._drinks,
                    CONF_FREE_AMOUNT: 0.0,
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
        return DrinkCounterOptionsFlowHandler(config_entry)


class DrinkCounterOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        self.config_entry = config_entry
        self._drinks: dict[str, float] = {}
        self._free_amount: float = 0.0
        self._users: list[str] = []

    async def async_step_init(self, user_input=None):
        self._drinks = self.hass.data.get(DOMAIN, {}).get("drinks", {}).copy()
        self._free_amount = self.hass.data.get(DOMAIN, {}).get("free_amount", 0.0)
        self._users = list(self.config_entry.data.get(CONF_USERS, []))
        return await self.async_step_menu()

    async def async_step_menu(self, user_input=None):
        if user_input is not None:
            action = user_input["action"]
            if action == "add":
                return await self.async_step_add_drink()
            if action == "remove":
                return await self.async_step_remove_drink()
            if action == "edit":
                return await self.async_step_edit_price()
            if action == "add_user":
                return await self.async_step_add_user()
            if action == "remove_user":
                return await self.async_step_remove_user()
            if action == "free_amount":
                return await self.async_step_set_free_amount()
            if action == "finish":
                return await self._update_drinks()
        schema = vol.Schema(
            {
                vol.Required("action"): vol.In(
                    [
                        "add",
                        "remove",
                        "edit",
                        "add_user",
                        "remove_user",
                        "free_amount",
                        "finish",
                    ]
                ),
            }
        )
        return self.async_show_form(step_id="menu", data_schema=schema)

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

    async def async_step_add_user(self, user_input=None):
        if user_input is not None:
            user = user_input[CONF_USER]
            if user not in self._users:
                self._users.append(user)
            if user_input.get("add_more"):
                return await self.async_step_add_user()
            return await self.async_step_menu()

        schema = vol.Schema(
            {
                vol.Required(CONF_USER): str,
                vol.Optional("add_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="add_user", data_schema=schema)

    async def async_step_remove_user(self, user_input=None):
        if user_input is not None:
            user = user_input[CONF_USER]
            if user in self._users and user != PRICE_LIST_USER:
                self._users.remove(user)
            if user_input.get("remove_more") and len(self._users) > 1:
                return await self.async_step_remove_user()
            return await self.async_step_menu()

        selectable = [u for u in self._users if u != PRICE_LIST_USER]
        if not selectable:
            return await self.async_step_menu()
        schema = vol.Schema(
            {
                vol.Required(CONF_USER): vol.In(selectable),
                vol.Optional("remove_more", default=False): bool,
            }
        )
        return self.async_show_form(step_id="remove_user", data_schema=schema)

    async def _update_drinks(self):
        # Update global drinks list before reloading entries so that new
        # sensors are created with the latest values during setup.
        self.hass.data.setdefault(DOMAIN, {})["drinks"] = self._drinks
        self.hass.data[DOMAIN]["free_amount"] = self._free_amount

        for entry in self.hass.config_entries.async_entries(DOMAIN):
            data = {
                CONF_USERS: self._users,
                CONF_DRINKS: self._drinks,
                CONF_FREE_AMOUNT: self._free_amount,
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
                CONF_USERS: self._users,
                CONF_DRINKS: self._drinks,
                CONF_FREE_AMOUNT: self._free_amount,
            },
        )
