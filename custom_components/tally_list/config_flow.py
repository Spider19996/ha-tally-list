"""Config flow for Tally List."""

from __future__ import annotations

import logging
from homeassistant import config_entries
from homeassistant.core import callback
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
    PRICE_LIST_USERS,
    get_cash_user_name,
    get_price_list_user,
)
from .base_flow import TallyListFlowHandler
from .flow_helpers import Step
from .options_flow import TallyListOptionsFlowHandler

_LOGGER = logging.getLogger(__name__)


class TallyListConfigFlow(config_entries.ConfigFlow, TallyListFlowHandler, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._user: str | None = None
        self._pending_users: list[str] = []
        self._create_price_user: bool = False
        self._user_selected: bool = False
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
        self._public_devices = user_input.get(CONF_PUBLIC_DEVICES, [])
        self._currency = user_input.get(CONF_CURRENCY, "€")
        self._enable_free_drinks = user_input.get(CONF_ENABLE_FREE_DRINKS, False)
        self._cash_user_name = get_cash_user_name(getattr(self.hass.config, "language", None))
        if CONF_CURRENCY not in user_input:
            user_input[CONF_CURRENCY] = self._currency
        if CONF_ENABLE_FREE_DRINKS not in user_input:
            user_input[CONF_ENABLE_FREE_DRINKS] = self._enable_free_drinks
        user_input[CONF_CASH_USER_NAME] = self._cash_user_name
        user_input[CONF_PUBLIC_DEVICES] = self._public_devices
        return self.async_create_entry(title=self._user, data=user_input)

    async def async_step_user(self, user_input=None):
        if not self._user_selected:
            self._cash_user_name = get_cash_user_name(getattr(self.hass.config, "language", None))
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
                    self._enable_free_drinks = entry.data.get(CONF_ENABLE_FREE_DRINKS, False)
                    self._cash_user_name = get_cash_user_name(getattr(self.hass.config, "language", None))
                    break
            self._user_selected = True
            return await self.async_step_menu()

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
                CONF_PUBLIC_DEVICES: self._public_devices,
                CONF_CURRENCY: self._currency,
                CONF_ENABLE_FREE_DRINKS: self._enable_free_drinks,
                CONF_CASH_USER_NAME: self._cash_user_name,
            },
        )

    async def _finalize_setup(self) -> None:
        self.hass.data.setdefault(DOMAIN, {})["drinks"] = self._drinks
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
                    CONF_USER: get_price_list_user(getattr(self.hass.config, "language", None)),
                    CONF_FREE_AMOUNT: self._free_amount,
                    CONF_DRINKS: self._drinks,
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return TallyListOptionsFlowHandler(config_entry)
