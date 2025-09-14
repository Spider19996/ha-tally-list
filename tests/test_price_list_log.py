import sys
import types
import csv
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch
import importlib.machinery
from importlib import import_module


def _setup_env(tmp_path):
    original_modules = set(sys.modules.keys())

    # Stub minimal Home Assistant and related modules
    ha = types.ModuleType("homeassistant")
    helpers = types.ModuleType("homeassistant.helpers")
    helpers.__path__ = []
    er_mod = types.ModuleType("homeassistant.helpers.entity_registry")
    helpers.entity_registry = er_mod
    selector_mod = types.ModuleType("homeassistant.helpers.selector")
    class IconSelector:  # pragma: no cover - simple stub
        pass
    selector_mod.IconSelector = IconSelector
    helpers.selector = selector_mod
    util_mod = types.ModuleType("homeassistant.util")
    utile_dt_mod = types.ModuleType("homeassistant.util.dt")
    utile_dt_mod.get_time_zone = ZoneInfo
    utile_dt_mod.now = datetime.now
    util_mod.dt = utile_dt_mod
    config_entries_mod = types.ModuleType("homeassistant.config_entries")
    class ConfigFlow:  # pragma: no cover - simple stub
        def __init_subclass__(cls, **kwargs):
            pass
    class OptionsFlow:  # pragma: no cover - simple stub
        def __init_subclass__(cls, **kwargs):
            pass
    config_entries_mod.ConfigFlow = ConfigFlow
    config_entries_mod.OptionsFlow = OptionsFlow
    config_entries_mod.SOURCE_IMPORT = "import"
    core_mod = types.ModuleType("homeassistant.core")
    def callback(func):  # pragma: no cover - simple stub
        return func
    core_mod.callback = callback
    vol_mod = types.ModuleType("voluptuous")
    sys.modules.update({
        "homeassistant": ha,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.entity_registry": er_mod,
        "homeassistant.helpers.selector": selector_mod,
        "homeassistant.util": util_mod,
        "homeassistant.util.dt": utile_dt_mod,
        "homeassistant.config_entries": config_entries_mod,
        "homeassistant.core": core_mod,
        "voluptuous": vol_mod,
    })

    # Prepare dummy tally_list package and stub sensor
    component_path = Path(__file__).resolve().parents[1] / "custom_components" / "tally_list"
    sys.path.append(str(component_path.parent))
    pkg = types.ModuleType("tally_list")
    pkg.__path__ = [str(component_path)]
    pkg.__spec__ = importlib.machinery.ModuleSpec(name="tally_list", loader=None, is_package=True)
    sys.modules["tally_list"] = pkg
    sensor_stub = types.ModuleType("tally_list.sensor")
    class PriceListFeedSensor:  # pragma: no cover - simple stub
        pass
    sensor_stub.PriceListFeedSensor = PriceListFeedSensor
    sys.modules["tally_list.sensor"] = sensor_stub

    # Import module under test
    config_flow = import_module("tally_list.config_flow")
    _write_price_list_log = config_flow._write_price_list_log

    class DummyConfig:
        def __init__(self, base_path):
            self._base_path = base_path

        def path(self, *parts):
            return str(Path(self._base_path, *parts))

    class DummyHass:
        def __init__(self, base_path):
            self.config = DummyConfig(base_path)

    hass = DummyHass(tmp_path)

    def _cleanup():
        sys.path.remove(str(component_path.parent))
        for mod in set(sys.modules.keys()) - original_modules:
            del sys.modules[mod]

    return hass, _write_price_list_log, _cleanup


def test_group_drinks_same_minute(tmp_path):
    hass, _write_price_list_log, cleanup = _setup_env(tmp_path)
    try:
        tz = ZoneInfo("Europe/Berlin")
        ts = datetime(2025, 9, 14, 1, 9, 30, tzinfo=tz)
        with patch("tally_list.config_flow.dt_util.now", return_value=ts):
            _write_price_list_log(hass, "Robin Zimmermann", "add_drink", "Robin Zimmermann:Bier+1")
            _write_price_list_log(hass, "Robin Zimmermann", "add_drink", "Robin Zimmermann:Limo+1")
            _write_price_list_log(hass, "Robin Zimmermann", "add_drink", "Robin Zimmermann:Wasser+1")
        path = Path(tmp_path, "tally_list", "price_list", "price_list_2025.csv")
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter=";"))
        assert rows[0] == ["Time", "User", "Action", "Details"]
        assert rows[1] == [
            "2025-09-14T01:09",
            "Robin Zimmermann",
            "add_drink",
            "Robin Zimmermann:Bier+1,Limo+1,Wasser+1",
        ]
        assert len(rows) == 2
    finally:
        cleanup()


def test_aggregate_same_drink(tmp_path):
    hass, _write_price_list_log, cleanup = _setup_env(tmp_path)
    try:
        tz = ZoneInfo("Europe/Berlin")
        ts = datetime(2025, 9, 14, 1, 22, 15, tzinfo=tz)
        with patch("tally_list.config_flow.dt_util.now", return_value=ts):
            for _ in range(4):
                _write_price_list_log(
                    hass,
                    "Robin Zimmermann",
                    "add_drink",
                    "Robin Zimmermann:Bier+1",
                )
        path = Path(tmp_path, "tally_list", "price_list", "price_list_2025.csv")
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter=";"))
        assert rows[1] == [
            "2025-09-14T01:22",
            "Robin Zimmermann",
            "add_drink",
            "Robin Zimmermann:Bier+4",
        ]
    finally:
        cleanup()


def test_free_drink_logged_separately(tmp_path):
    hass, _write_price_list_log, cleanup = _setup_env(tmp_path)
    try:
        tz = ZoneInfo("Europe/Berlin")
        ts = datetime(2025, 9, 14, 1, 9, 30, tzinfo=tz)
        with patch("tally_list.config_flow.dt_util.now", return_value=ts):
            _write_price_list_log(
                hass,
                "Robin Zimmermann",
                "add_drink",
                "Robin Zimmermann:Bier+1",
            )
            _write_price_list_log(
                hass,
                "Robin Zimmermann",
                "add_free_drink",
                "Robin Zimmermann:Bier+1",
            )
        path = Path(tmp_path, "tally_list", "price_list", "price_list_2025.csv")
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter=";"))
        assert rows[1] == [
            "2025-09-14T01:09",
            "Robin Zimmermann",
            "add_drink",
            "Robin Zimmermann:Bier+1",
        ]
        assert rows[2] == [
            "2025-09-14T01:09",
            "Robin Zimmermann",
            "add_free_drink",
            "Robin Zimmermann:Bier+1",
        ]
        assert len(rows) == 3
    finally:
        cleanup()
