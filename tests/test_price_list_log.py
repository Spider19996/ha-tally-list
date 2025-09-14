import sys
import types
import csv
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch, AsyncMock
import importlib.machinery
from importlib import import_module
import pytest


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
    const_mod = import_module("tally_list.const")
    _write_price_list_log = config_flow._write_price_list_log
    _log_price_change = config_flow._log_price_change
    OptionsFlowHandler = config_flow.TallyListOptionsFlowHandler

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

    return (
        hass,
        _write_price_list_log,
        _log_price_change,
        OptionsFlowHandler,
        const_mod,
        _cleanup,
    )


def test_group_drinks_same_minute(tmp_path):
    hass, _write_price_list_log, _, _, _, cleanup = _setup_env(tmp_path)
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
    hass, _write_price_list_log, _, _, _, cleanup = _setup_env(tmp_path)
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
    hass, _write_price_list_log, _, _, _, cleanup = _setup_env(tmp_path)
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


@pytest.mark.asyncio
async def test_log_when_price_changed(tmp_path):
    hass, _, _, OptionsFlowHandler, const, cleanup = _setup_env(tmp_path)
    try:
        hass.auth = types.SimpleNamespace(current_user=types.SimpleNamespace(id="user-1"))
        flow = OptionsFlowHandler(config_entry=None)
        flow.hass = hass
        flow.context = {}
        flow.async_step_menu = AsyncMock(return_value=None)
        flow._user_id = "user-1"
        flow._drinks = {"Bier": 1.6}
        flow._drink_icons = {"Bier": "mdi:beer"}
        flow._edit_drink = "Bier"
        with patch("tally_list.config_flow._log_price_change", AsyncMock()) as log_mock:
            await flow.async_step_edit_price({
                const.CONF_PRICE: 1.7,
                const.CONF_ICON: "mdi:beer",
            })
            log_mock.assert_awaited_once_with(
                hass,
                "user-1",
                "edit_drink",
                "Bier:1.6->1.7",
            )
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_no_log_when_price_unchanged(tmp_path):
    hass, _, _, OptionsFlowHandler, const, cleanup = _setup_env(tmp_path)
    try:
        hass.auth = types.SimpleNamespace(current_user=types.SimpleNamespace(id="user-1"))
        flow = OptionsFlowHandler(config_entry=None)
        flow.hass = hass
        flow.context = {}
        flow.async_step_menu = AsyncMock(return_value=None)
        flow._user_id = "user-1"
        flow._drinks = {"Bier": 1.6}
        flow._drink_icons = {"Bier": "mdi:beer"}
        flow._edit_drink = "Bier"
        with patch("tally_list.config_flow._log_price_change", AsyncMock()) as log_mock:
            await flow.async_step_edit_price({
                const.CONF_PRICE: 1.6,
                const.CONF_ICON: "mdi:beer",
            })
            log_mock.assert_not_called()
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_log_uses_context_user(tmp_path):
    hass, _, _, OptionsFlowHandler, const, cleanup = _setup_env(tmp_path)
    try:
        flow = OptionsFlowHandler(config_entry=None)
        flow.hass = hass
        flow.context = {"user_id": "user-ctx"}
        flow.async_step_menu = AsyncMock(return_value=None)
        flow._user_id = "user-ctx"
        flow._drinks = {"Bier": 1.6}
        flow._drink_icons = {"Bier": "mdi:beer"}
        flow._edit_drink = "Bier"
        with patch("tally_list.config_flow._log_price_change", AsyncMock()) as log_mock:
            await flow.async_step_edit_price({
                const.CONF_PRICE: 1.7,
                const.CONF_ICON: "mdi:beer",
            })
            log_mock.assert_awaited_once_with(
                hass,
                "user-ctx",
                "edit_drink",
                "Bier:1.6->1.7",
            )
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_log_price_change_uses_username(tmp_path):
    hass, _write_price_list_log, _log_price_change, _, const, cleanup = _setup_env(tmp_path)
    try:
        hass.data = {const.DOMAIN: {}}
        hass.states = types.SimpleNamespace(async_all=lambda domain: [])
        mock_user = types.SimpleNamespace(name=None, username="tester")
        hass.auth = types.SimpleNamespace(
            async_get_user=AsyncMock(return_value=mock_user), current_user=None
        )
        hass.async_add_executor_job = AsyncMock()
        await _log_price_change(
            hass,
            "user-id",
            "edit_drink",
            "Bier:1.6->1.7",
        )
        hass.async_add_executor_job.assert_awaited_once()
        args = hass.async_add_executor_job.await_args.args
        assert args[2] == "tester"
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_user_id_preserved_after_init(tmp_path):
    hass, _, _, OptionsFlowHandler, const, cleanup = _setup_env(tmp_path)
    try:
        hass.auth = types.SimpleNamespace(current_user=types.SimpleNamespace(id="user-1"))
        hass.data = {const.DOMAIN: {}}
        hass.config.language = "en"
        flow = OptionsFlowHandler(config_entry=None)
        flow.hass = hass
        flow.context = {}
        flow.async_step_menu = AsyncMock(return_value=None)
        await flow.async_step_init()
        hass.auth.current_user = None
        flow._drinks = {"Bier": 1.6}
        flow._drink_icons = {"Bier": "mdi:beer"}
        flow._edit_drink = "Bier"
        with patch("tally_list.config_flow._log_price_change", AsyncMock()) as log_mock:
            await flow.async_step_edit_price({
                const.CONF_PRICE: 1.7,
                const.CONF_ICON: "mdi:beer",
            })
            log_mock.assert_awaited_once_with(
                hass,
                "user-1",
                "edit_drink",
                "Bier:1.6->1.7",
            )
    finally:
        cleanup()
