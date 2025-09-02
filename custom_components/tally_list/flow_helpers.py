from __future__ import annotations

from enum import Enum
from typing import Any, Iterable, Mapping

import voluptuous as vol

from .const import PRICE_LIST_USERS


class Step(str, Enum):
    """Flow step names used by config and options flows."""

    USER = "user"
    MENU = "menu"
    DRINKS = "drinks"
    ADD_DRINK = "add_drink"
    REMOVE_DRINK = "remove_drink"
    EDIT_PRICE = "edit_price"
    CURRENCY = "currency"
    FREE_AMOUNT = "free_amount"
    FREE_DRINKS = "free_drinks"
    FREE_DRINKS_CONFIRM = "free_drinks_confirm"
    EXCLUDE = "exclude"
    INCLUDE = "include"
    AUTHORIZE = "authorize"
    UNAUTHORIZE = "unauthorize"
    AUTHORIZE_PUBLIC = "authorize_public"
    UNAUTHORIZE_PUBLIC = "unauthorize_public"
    ADD_EXCLUDED_USER = "add_excluded_user"
    REMOVE_EXCLUDED_USER = "remove_excluded_user"
    ADD_OVERRIDE_USER = "add_override_user"
    REMOVE_OVERRIDE_USER = "remove_override_user"
    ADD_PUBLIC_USER = "add_public_user"
    REMOVE_PUBLIC_USER = "remove_public_user"
    FINISH = "finish"
    BACK = "back"
    CLEANUP = "cleanup"
    CLEANUP_RESULT = "cleanup_result"
    CLEANUP_RESULT_EMPTY = "cleanup_result_empty"
    DELETE = "delete"


def parse_drinks(value: str) -> dict[str, float]:
    """Parse a comma-separated drink string into a dict."""
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


def build_choice_schema(key: str, options: Iterable[str], more_key: str | None = None) -> vol.Schema:
    """Return a schema for selecting from a list of options."""
    schema: dict = {vol.Required(key): vol.In(list(options))}
    if more_key is not None:
        schema[vol.Optional(more_key, default=False)] = bool
    return vol.Schema(schema)


def get_available_persons(registry: Any, states: Mapping[str, Any], exclude: Iterable[str]) -> list[str]:
    """Return available person names from the registry excluding provided names."""
    persons = [
        entry.original_name or entry.name or entry.entity_id
        for entry in registry.entities.values()
        if entry.domain == "person"
        and (
            (state := states.get(entry.entity_id))
            and state.attributes.get("user_id")
        )
    ]
    return [p for p in persons if p not in exclude and p not in PRICE_LIST_USERS]
