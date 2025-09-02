from __future__ import annotations

from typing import Iterable

import voluptuous as vol
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_CURRENCY,
    CONF_DRINK,
    CONF_DRINKS,
    CONF_ENABLE_FREE_DRINKS,
    CONF_FREE_AMOUNT,
    CONF_OVERRIDE_USERS,
    CONF_PRICE,
    CONF_PUBLIC_DEVICES,
    CONF_USER,
    CONF_EXCLUDED_USERS,
)
from .flow_helpers import Step, build_choice_schema, get_available_persons


class TallyListFlowHandler:
    """Common logic for Tally List config and options flows."""

    MENU_OPTIONS: list[Step] = [Step.USER, Step.DRINKS, Step.FINISH]
    DRINK_MENU: list[Step] = [
        Step.ADD_DRINK,
        Step.REMOVE_DRINK,
        Step.EDIT_PRICE,
        Step.CURRENCY,
        Step.BACK,
    ]

    def __init__(self) -> None:
        self._drinks: dict[str, float] = {}
        self._free_amount: float = 0.0
        self._excluded_users: list[str] = []
        self._override_users: list[str] = []
        self._public_devices: list[str] = []
        self._currency: str = "€"
        self._enable_free_drinks: bool = False

    async def async_step_menu(self, user_input=None):
        return self.async_show_menu(
            step_id=Step.MENU,
            menu_options=[step.value for step in self.MENU_OPTIONS],
        )

    async def async_step_drinks(self, user_input=None):
        return self.async_show_menu(
            step_id=Step.DRINKS,
            menu_options=[step.value for step in self.DRINK_MENU],
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
        return self.async_show_form(step_id=Step.CURRENCY, data_schema=schema)

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
        return self.async_show_form(step_id=Step.ADD_DRINK, data_schema=schema)

    async def async_step_remove_drink(self, user_input=None):
        if user_input is not None:
            drink = user_input[CONF_DRINK]
            self._drinks.pop(drink, None)
            if user_input.get("remove_more") and self._drinks:
                return await self.async_step_remove_drink()
            return await self.async_step_menu()
        if not self._drinks:
            return await self.async_step_menu()
        schema = build_choice_schema(CONF_DRINK, self._drinks.keys(), "remove_more")
        return self.async_show_form(step_id=Step.REMOVE_DRINK, data_schema=schema)

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
        return self.async_show_form(step_id=Step.EDIT_PRICE, data_schema=schema)

    async def async_step_set_free_amount(self, user_input=None):
        if user_input is not None:
            self._free_amount = float(user_input[CONF_FREE_AMOUNT])
            return await self.async_step_menu()
        schema = vol.Schema(
            {vol.Required(CONF_FREE_AMOUNT, default=self._free_amount): vol.Coerce(float)}
        )
        return self.async_show_form(step_id=Step.FREE_AMOUNT, data_schema=schema)
    async def async_step_add_excluded_user(self, user_input=None):
        registry = er.async_get(self.hass)
        persons = get_available_persons(registry, self.hass.states, self._excluded_users)
        if not persons:
            return await self.async_step_menu()
        if user_input is not None:
            user = user_input[CONF_USER]
            self._excluded_users.append(user)
            if user_input.get("add_more") and len(persons) > 1:
                return await self.async_step_add_excluded_user()
            return await self.async_step_menu()
        schema = build_choice_schema(CONF_USER, persons, "add_more")
        return self.async_show_form(step_id=Step.ADD_EXCLUDED_USER, data_schema=schema)

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
        schema = build_choice_schema(CONF_USER, self._excluded_users, "remove_more")
        return self.async_show_form(step_id=Step.REMOVE_EXCLUDED_USER, data_schema=schema)

    async def async_step_add_override_user(self, user_input=None):
        registry = er.async_get(self.hass)
        persons = get_available_persons(registry, self.hass.states, self._override_users)
        if not persons:
            return await self.async_step_menu()
        if user_input is not None:
            user = user_input[CONF_USER]
            self._override_users.append(user)
            if user_input.get("add_more") and len(persons) > 1:
                return await self.async_step_add_override_user()
            return await self.async_step_menu()
        schema = build_choice_schema(CONF_USER, persons, "add_more")
        return self.async_show_form(step_id=Step.ADD_OVERRIDE_USER, data_schema=schema)

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
        schema = build_choice_schema(CONF_USER, self._override_users, "remove_more")
        return self.async_show_form(step_id=Step.REMOVE_OVERRIDE_USER, data_schema=schema)

    async def async_step_add_public_user(self, user_input=None):
        registry = er.async_get(self.hass)
        persons = get_available_persons(registry, self.hass.states, self._public_devices)
        if not persons:
            return await self.async_step_menu()
        if user_input is not None:
            user = user_input[CONF_USER]
            self._public_devices.append(user)
            if user_input.get("add_more") and len(persons) > 1:
                return await self.async_step_add_public_user()
            return await self.async_step_menu()
        schema = build_choice_schema(CONF_USER, persons, "add_more")
        return self.async_show_form(step_id=Step.ADD_PUBLIC_USER, data_schema=schema)

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
        schema = build_choice_schema(CONF_USER, self._public_devices, "remove_more")
        return self.async_show_form(step_id=Step.REMOVE_PUBLIC_USER, data_schema=schema)

    async def async_step_authorize(self, user_input=None):
        return await self.async_step_add_override_user(user_input)

    async def async_step_unauthorize(self, user_input=None):
        return await self.async_step_remove_override_user(user_input)

    async def async_step_authorize_public(self, user_input=None):
        return await self.async_step_add_public_user(user_input)

    async def async_step_unauthorize_public(self, user_input=None):
        return await self.async_step_remove_public_user(user_input)

    async def async_step_free_drinks(self, user_input=None):
        if user_input is not None:
            enable = user_input[CONF_ENABLE_FREE_DRINKS]
            if self._enable_free_drinks and not enable:
                return await self.async_step_free_drinks_confirm()
            self._enable_free_drinks = enable
            return await self.async_step_menu()
        schema = vol.Schema(
            {vol.Required(CONF_ENABLE_FREE_DRINKS, default=self._enable_free_drinks): bool}
        )
        return self.async_show_form(step_id=Step.FREE_DRINKS, data_schema=schema)

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
            step_id=Step.FREE_DRINKS_CONFIRM, data_schema=schema, errors=errors
        )
