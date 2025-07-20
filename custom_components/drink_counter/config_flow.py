"""Config flow for Drink Counter."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import DOMAIN, CONF_USER, CONF_DRINKS


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

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                drinks = _parse_drinks(user_input[CONF_DRINKS])
            except ValueError:
                errors[CONF_DRINKS] = "invalid_drinks"
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_USER],
                    data={CONF_USER: user_input[CONF_USER], CONF_DRINKS: drinks},
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_USER): str,
                vol.Required(CONF_DRINKS): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return DrinkCounterOptionsFlowHandler(config_entry)


class DrinkCounterOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        errors = {}
        if user_input is not None:
            try:
                drinks = _parse_drinks(user_input[CONF_DRINKS])
            except ValueError:
                errors[CONF_DRINKS] = "invalid_drinks"
            if not errors:
                return self.async_create_entry(title="", data={CONF_DRINKS: drinks})
        current = ",".join(
            f"{name}={price}" for name, price in self.config_entry.data.get(CONF_DRINKS, {}).items()
        )
        schema = vol.Schema(
            {vol.Required(CONF_DRINKS, default=current): str}
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
