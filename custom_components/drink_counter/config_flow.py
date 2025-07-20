"""Config flow for Drink Counter."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_USER,
    CONF_DRINKS,
    CONF_DRINK,
    CONF_PRICE,
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

    VERSION = 1

    def __init__(self) -> None:
        self._user: str | None = None
        self._drinks: dict[str, float] = {}

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._user = user_input[CONF_USER]
            entries = self.hass.config_entries.async_entries(DOMAIN)
            for entry in entries:
                if CONF_DRINKS in entry.data:
                    self._drinks = entry.data[CONF_DRINKS]
                    return self.async_create_entry(
                        title=self._user,
                        data={CONF_USER: self._user},
                    )
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
                title=self._user,
                data={CONF_USER: self._user, CONF_DRINKS: self._drinks},
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

    async def async_step_init(self, user_input=None):
        self._drinks = self.hass.data.get(DOMAIN, {}).get("drinks", {}).copy()
        return await self.async_step_menu()

    async def async_step_menu(self, user_input=None):
        if user_input is not None:
            action = user_input["action"]
            if action == "add":
                return await self.async_step_add_drink()
            if action == "remove":
                return await self.async_step_remove_drink()
            if action == "finish":
                return await self._update_drinks()
        schema = vol.Schema({vol.Required("action"): vol.In(["add", "remove", "finish"])} )
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

    async def _update_drinks(self):
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            data = {CONF_USER: entry.data[CONF_USER], CONF_DRINKS: self._drinks}
            self.hass.config_entries.async_update_entry(entry, data=data)
        self.hass.data.setdefault(DOMAIN, {})["drinks"] = self._drinks
        return self.async_create_entry(title="", data={CONF_DRINKS: self._drinks})
