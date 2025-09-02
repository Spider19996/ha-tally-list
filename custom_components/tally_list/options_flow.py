from __future__ import annotations

import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_CASH_USER_NAME,
    CONF_CURRENCY,
    CONF_DRINKS,
    CONF_ENABLE_FREE_DRINKS,
    CONF_EXCLUDED_USERS,
    CONF_FREE_AMOUNT,
    CONF_OVERRIDE_USERS,
    CONF_PUBLIC_DEVICES,
    CONF_USER,
    DOMAIN,
    get_cash_user_name,
)
from .base_flow import TallyListFlowHandler
from .flow_helpers import Step

_LOGGER = logging.getLogger(__name__)


class TallyListOptionsFlowHandler(config_entries.OptionsFlow, TallyListFlowHandler):
    """Handle options for existing entries."""

    MENU_OPTIONS = [Step.USER, Step.DRINKS, Step.CLEANUP, Step.DELETE, Step.FINISH]
    DRINK_MENU = [
        Step.ADD_DRINK,
        Step.REMOVE_DRINK,
        Step.EDIT_PRICE,
        Step.CURRENCY,
        Step.FREE_DRINKS,
        Step.BACK,
    ]

    def __init__(self, config_entry):
        super().__init__()
        self.config_entry = config_entry
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
        self._public_devices = (
            self.hass.data.get(DOMAIN, {}).get(CONF_PUBLIC_DEVICES, [])
        ).copy()
        self._currency = self.hass.data.get(DOMAIN, {}).get(CONF_CURRENCY, "€")
        self._enable_free_drinks = self.hass.data.get(DOMAIN, {}).get(
            CONF_ENABLE_FREE_DRINKS, False
        )
        self._cash_user_name = get_cash_user_name(getattr(self.hass.config, "language", None))
        return await self.async_step_menu()

    async def async_step_user(self, user_input=None):
        return self.async_show_menu(
            step_id=Step.USER,
            menu_options=[
                Step.FREE_AMOUNT.value,
                Step.EXCLUDE.value,
                Step.INCLUDE.value,
                Step.AUTHORIZE.value,
                Step.UNAUTHORIZE.value,
                Step.AUTHORIZE_PUBLIC.value,
                Step.UNAUTHORIZE_PUBLIC.value,
                Step.BACK.value,
            ],
        )

    async def async_step_free_drinks(self, user_input=None):
        if user_input is not None:
            enable = user_input[CONF_ENABLE_FREE_DRINKS]
            if self._enable_free_drinks and not enable:
                return await self.async_step_free_drinks_confirm()
            self._enable_free_drinks = enable
            return await self.async_step_drinks()
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
                return await self.async_step_drinks()
            errors["base"] = "confirmation_required"
        schema = vol.Schema({vol.Required("confirm"): str})
        return self.async_show_form(
            step_id=Step.FREE_DRINKS_CONFIRM, data_schema=schema, errors=errors
        )

    async def async_step_cleanup(self, user_input=None):
        errors = {}
        if user_input is not None:
            confirmation = user_input.get("confirm", "").strip().upper()
            if confirmation in {"JA ICH WILL", "YES I WANT"}:
                removed = await self._cleanup_unused_entities()
                if removed:
                    return self.async_show_form(
                        step_id=Step.CLEANUP_RESULT,
                        description_placeholders={"sensors": "\n- ".join(sorted(removed))},
                    )
                return self.async_show_form(step_id=Step.CLEANUP_RESULT_EMPTY)
            errors["base"] = "invalid_confirmation"
        schema = vol.Schema({vol.Required("confirm"): str})
        return self.async_show_form(step_id=Step.CLEANUP, data_schema=schema, errors=errors)

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
        return self.async_show_form(step_id=Step.DELETE, data_schema=schema, errors=errors)

    async def async_step_finish(self, user_input=None):
        return await self._update_drinks()

    async def _cleanup_unused_entities(self) -> list[str]:
        registry = er.async_get(self.hass)
        to_remove: list[str] = []
        for entity_entry in list(registry.entities.values()):
            if entity_entry.domain == "sensor" and entity_entry.platform == DOMAIN:
                if entity_entry.entity_id not in self.hass.data.get(DOMAIN, {})\
                    .get("sensors", []):
                    to_remove.append(entity_entry.entity_id)
                    await registry.async_remove(entity_entry.entity_id)
        return to_remove

    async def _delete_all_entries(self) -> None:
        entries = list(self.hass.config_entries.async_entries(DOMAIN))
        for entry in entries:
            await self.hass.config_entries.async_remove(entry.entry_id)

        registry = er.async_get(self.hass)
        for entity_entry in list(registry.entities.values()):
            if entity_entry.domain == "sensor" and entity_entry.platform == DOMAIN:
                try:
                    await registry.async_remove(entity_entry.entity_id)
                except Exception as exc:  # pragma: no cover
                    _LOGGER.error("Failed to remove %s: %s", entity_entry.entity_id, exc)

        self.hass.data.pop(DOMAIN, None)

    async def _update_drinks(self):
        self.hass.data.setdefault(DOMAIN, {})["drinks"] = self._drinks
        self.hass.data[DOMAIN]["free_amount"] = self._free_amount
        self.hass.data[DOMAIN][CONF_EXCLUDED_USERS] = self._excluded_users
        self.hass.data[DOMAIN][CONF_OVERRIDE_USERS] = self._override_users
        self.hass.data[DOMAIN][CONF_PUBLIC_DEVICES] = self._public_devices
        self.hass.data[DOMAIN][CONF_CURRENCY] = self._currency
        self.hass.data[DOMAIN][CONF_CASH_USER_NAME] = self._cash_user_name
        entries = self.hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            data = {
                CONF_USER: entry.data[CONF_USER],
                CONF_DRINKS: self._drinks,
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
                CONF_FREE_AMOUNT: self._free_amount,
                CONF_EXCLUDED_USERS: self._excluded_users,
                CONF_OVERRIDE_USERS: self._override_users,
                CONF_PUBLIC_DEVICES: self._public_devices,
                CONF_CURRENCY: self._currency,
                CONF_ENABLE_FREE_DRINKS: self._enable_free_drinks,
                CONF_CASH_USER_NAME: self._cash_user_name,
            },
        )
