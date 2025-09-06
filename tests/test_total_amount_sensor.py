import sys
from pathlib import Path
import types


# Stub minimal Home Assistant modules required for imports
ha = types.ModuleType("homeassistant")
components = types.ModuleType("homeassistant.components")
sensor_comp = types.ModuleType("homeassistant.components.sensor")


class SensorEntity:  # pragma: no cover - simple stub
    pass


sensor_comp.SensorEntity = SensorEntity

helpers = types.ModuleType("homeassistant.helpers")
helpers.__path__ = []  # mark as package
event_mod = types.ModuleType("homeassistant.helpers.event")


def async_track_time_interval(*_args, **_kwargs):  # pragma: no cover - stub
    return None


event_mod.async_track_time_interval = async_track_time_interval
restore_mod = types.ModuleType("homeassistant.helpers.restore_state")


class RestoreEntity:  # pragma: no cover - simple stub
    pass


restore_mod.RestoreEntity = RestoreEntity
helpers.event = event_mod
helpers.restore_state = restore_mod
typing_mod = types.ModuleType("homeassistant.helpers.typing")


class ConfigType(dict):  # pragma: no cover - simple stub
    pass


typing_mod.ConfigType = ConfigType

config_entries_mod = types.ModuleType("homeassistant.config_entries")


class ConfigEntry:  # pragma: no cover - simple stub
    pass


config_entries_mod.ConfigEntry = ConfigEntry
core_mod = types.ModuleType("homeassistant.core")


class HomeAssistant:  # pragma: no cover - simple stub
    pass


core_mod.HomeAssistant = HomeAssistant
util_mod = types.ModuleType("homeassistant.util")


def slugify(value):  # pragma: no cover - simple stub
    return value.lower().replace(" ", "_")


util_mod.slugify = slugify
sys.modules.update(
    {
        "homeassistant": ha,
        "homeassistant.components": components,
        "homeassistant.components.sensor": sensor_comp,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.event": event_mod,
        "homeassistant.helpers.restore_state": restore_mod,
        "homeassistant.helpers.typing": typing_mod,
        "homeassistant.config_entries": config_entries_mod,
        "homeassistant.core": core_mod,
        "homeassistant.util": util_mod,
    }
)

# Make custom_component modules importable
component_path = Path(__file__).resolve().parents[1] / "custom_components" / "tally_list"
sys.path.append(str(component_path.parent))

# Create a dummy package to avoid executing the real __init__.py
import importlib.machinery

pkg = types.ModuleType("tally_list")
pkg.__path__ = [str(component_path)]
pkg.__spec__ = importlib.machinery.ModuleSpec(
    name="tally_list", loader=None, is_package=True
)
sys.modules["tally_list"] = pkg

from importlib import import_module  # noqa: E402

const = import_module("tally_list.const")  # noqa: E402
sensor_module = import_module("tally_list.sensor")  # noqa: E402

DOMAIN = const.DOMAIN
CONF_USER = const.CONF_USER
CONF_CASH_USER_NAME = const.CONF_CASH_USER_NAME
TotalAmountSensor = sensor_module.TotalAmountSensor


class DummyHass:
    def __init__(self, data, language="en"):
        self.data = data
        self.config = types.SimpleNamespace(language=language)


class DummyConfigEntry:
    def __init__(self, entry_id, user):
        self.entry_id = entry_id
        self.data = {CONF_USER: user}


def test_total_amount_sensor_regular_user():
    entry = DummyConfigEntry("abc", "Alice")
    hass = DummyHass(
        {
            DOMAIN: {
                "drinks": {"Beer": 2.0},
                "free_amount": 1.5,
                CONF_CASH_USER_NAME: "Cash",
                entry.entry_id: {"counts": {"Beer": 1}},
            }
        }
    )
    sensor = TotalAmountSensor(hass, entry)
    assert sensor.native_value == 0.5


def test_total_amount_sensor_cash_user_ignores_free_amount():
    entry = DummyConfigEntry("xyz", "Cash")
    hass = DummyHass(
        {
            DOMAIN: {
                "drinks": {"Beer": 2.0},
                "free_amount": 1.5,
                CONF_CASH_USER_NAME: "Cash",
                entry.entry_id: {"counts": {"Beer": 1}},
            }
        }
    )
    sensor = TotalAmountSensor(hass, entry)
    assert sensor.native_value == 2.0

