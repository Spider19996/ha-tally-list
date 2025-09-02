import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1] / "custom_components" / "tally_list"))

from utils import get_person_name


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
    def __init__(self, states):
        self.states = DummyStates(states)


def test_get_person_name_found():
    hass = DummyHass([DummyState("Alice", "user-1"), DummyState("Bob", "user-2")])
    assert get_person_name(hass, "user-2") == "Bob"


def test_get_person_name_not_found():
    hass = DummyHass([])
    assert get_person_name(hass, "user-1") is None


def test_get_person_name_no_user_id():
    hass = DummyHass([DummyState("Alice", "user-1")])
    assert get_person_name(hass, None) is None

