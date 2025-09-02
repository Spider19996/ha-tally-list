import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "custom_components" / "tally_list"))

from const import DOMAIN, CONF_CASH_USER_NAME, CASH_USER_SLUG
from utils import get_person_name, get_user_slug


class DummyState:
    def __init__(self, name, user_id):
        self.name = name
        self.attributes = {"user_id": user_id}


class DummyStates:
    def __init__(self, states):
        self._states = states

    def async_all(self, domain):
        assert domain == "person"
        return self._states


class DummyHass:
    def __init__(self, states, data=None):
        self.states = DummyStates(states)
        self.data = data or {}


def test_get_person_name_found():
    hass = DummyHass([DummyState("Alice", "user-1"), DummyState("Bob", "user-2")])
    assert get_person_name(hass, "user-2") == "Bob"


def test_get_person_name_not_found():
    hass = DummyHass([])
    assert get_person_name(hass, "user-1") is None


def test_get_person_name_no_user_id():
    hass = DummyHass([DummyState("Alice", "user-1")])
    assert get_person_name(hass, None) is None


def test_get_user_slug_regular():
    hass = DummyHass([], {DOMAIN: {CONF_CASH_USER_NAME: "Cash"}})
    assert get_user_slug(hass, "John Doe") == "john_doe"


def test_get_user_slug_cash_user():
    hass = DummyHass([], {DOMAIN: {CONF_CASH_USER_NAME: "Cash"}})
    assert get_user_slug(hass, "cash") == CASH_USER_SLUG

