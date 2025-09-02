import importlib
import pathlib
import sys
from types import SimpleNamespace, ModuleType

import pytest
import voluptuous as vol

# Create a dummy package structure so flow_helpers can resolve relative imports
pkg = ModuleType("custom_components")
pkg.__path__ = []
sys.modules.setdefault("custom_components", pkg)
subpkg = ModuleType("custom_components.tally_list")
subpkg.__path__ = [str(pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "tally_list")]
sys.modules["custom_components.tally_list"] = subpkg

flow_helpers = importlib.import_module("custom_components.tally_list.flow_helpers")
from custom_components.tally_list.const import PRICE_LIST_USER_EN

build_choice_schema = flow_helpers.build_choice_schema
get_available_persons = flow_helpers.get_available_persons
parse_drinks = flow_helpers.parse_drinks


def test_parse_drinks():
    result = parse_drinks("cola=1.5, beer=2")
    assert result == {"cola": 1.5, "beer": 2.0}
    with pytest.raises(ValueError):
        parse_drinks("invalid")


def test_build_choice_schema():
    schema = build_choice_schema("drink", ["a", "b"], "more")
    data = schema({"drink": "a", "more": True})
    assert data["drink"] == "a" and data["more"] is True
    with pytest.raises(vol.Invalid):
        schema({"drink": "c"})


def test_get_available_persons():
    registry_entry = SimpleNamespace(
        entity_id="person.one", domain="person", name="One", original_name=None
    )
    registry = SimpleNamespace(entities={"person.one": registry_entry})
    state = SimpleNamespace(attributes={"user_id": "123"})
    states = {"person.one": state}
    persons = get_available_persons(registry, states, [PRICE_LIST_USER_EN])
    assert persons == ["One"]
    persons = get_available_persons(registry, states, ["One"])
    assert persons == []
