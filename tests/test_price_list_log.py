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
    http_mod = types.ModuleType("homeassistant.helpers.http")
    from contextvars import ContextVar
    http_mod.current_request = ContextVar("current_request", default=None)
    helpers.http = http_mod
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
    vol_mod.Schema = lambda schema, *args, **kwargs: schema
    vol_mod.Required = lambda key, default=None: key
    vol_mod.Optional = lambda key, default=None: key
    vol_mod.Coerce = lambda typ: typ
    sys.modules.update({
        "homeassistant": ha,
        "homeassistant.helpers": helpers,
        "homeassistant.helpers.entity_registry": er_mod,
        "homeassistant.helpers.selector": selector_mod,
        "homeassistant.helpers.http": http_mod,
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


def test_group_other_user_same_minute(tmp_path):
    hass, _write_price_list_log, _, _, _, cleanup = _setup_env(tmp_path)
    try:
        tz = ZoneInfo("Europe/Berlin")
        ts = datetime(2025, 9, 14, 1, 33, 0, tzinfo=tz)
        with patch("tally_list.config_flow.dt_util.now", return_value=ts):
            _write_price_list_log(
                hass,
                "Robin Zimmermann",
                "add_drink",
                "Sebastian Schumans:Bitburger+1",
            )
            _write_price_list_log(
                hass,
                "Robin Zimmermann",
                "add_drink",
                "Sebastian Schumans:Limo+1",
            )
        path = Path(tmp_path, "tally_list", "price_list", "price_list_2025.csv")
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter=";"))
        assert rows[1] == [
            "2025-09-14T01:33",
            "Robin Zimmermann",
            "add_drink",
            "Sebastian Schumans:Bitburger+1,Limo+1",
        ]
    finally:
        cleanup()


def test_aggregate_same_drink_other_user(tmp_path):
    hass, _write_price_list_log, _, _, _, cleanup = _setup_env(tmp_path)
    try:
        tz = ZoneInfo("Europe/Berlin")
        ts = datetime(2025, 9, 14, 1, 44, 0, tzinfo=tz)
        with patch("tally_list.config_flow.dt_util.now", return_value=ts):
            for _ in range(2):
                _write_price_list_log(
                    hass,
                    "Robin Zimmermann",
                    "add_drink",
                    "Sebastian Schumans:Bitburger+1",
                )
        path = Path(tmp_path, "tally_list", "price_list", "price_list_2025.csv")
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f, delimiter=";"))
        assert rows[1] == [
            "2025-09-14T01:44",
            "Robin Zimmermann",
            "add_drink",
            "Sebastian Schumans:Bitburger+2",
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
async def test_options_flow_add_remove_logged_separately(tmp_path):
    hass, _, _, OptionsFlowHandler, const, cleanup = _setup_env(tmp_path)
    try:
        hass.auth = types.SimpleNamespace(current_user=types.SimpleNamespace(id="user-1"))
        flow = OptionsFlowHandler(config_entry=None)
        flow.hass = hass
        flow.context = {}
        flow.async_step_menu = AsyncMock(return_value=None)
        flow._user_id = "user-1"
        with patch("tally_list.config_flow._log_price_change", AsyncMock()) as log_mock:
            await flow.async_step_add_drink({
                const.CONF_DRINK: "Bier",
                const.CONF_PRICE: 1.5,
                const.CONF_ICON: "mdi:beer",
            })
            log_mock.assert_awaited_once_with(
                hass, "user-1", "add_drink_type", "Bier=1.5"
            )
        flow._drinks = {"Bier": 1.5}
        flow._drink_icons = {"Bier": "mdi:beer"}
        with patch("tally_list.config_flow._log_price_change", AsyncMock()) as log_mock:
            await flow.async_step_remove_drink({const.CONF_DRINK: "Bier"})
            log_mock.assert_awaited_once_with(
                hass, "user-1", "remove_drink_type", "Bier"
            )
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
        flow._user_id = None
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


@pytest.mark.asyncio
async def test_log_uses_request_user(tmp_path):
    hass, _, _, OptionsFlowHandler, const, cleanup = _setup_env(tmp_path)
    try:
        from homeassistant.helpers.http import current_request

        request = {"hass_user": types.SimpleNamespace(id="req-user")}
        token = current_request.set(request)

        flow = OptionsFlowHandler(config_entry=None)
        flow.hass = hass
        flow.context = {}
        flow.async_step_menu = AsyncMock(return_value=None)
        flow._user_id = None
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
                "req-user",
                "edit_drink",
                "Bier:1.6->1.7",
            )
        current_request.reset(token)
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_no_log_when_drinks_logging_disabled(tmp_path):
    hass, _write_price_list_log, _log_price_change, _, const, cleanup = _setup_env(tmp_path)
    try:
        hass.data = {
            const.DOMAIN: {
                const.CONF_ENABLE_LOGGING: True,
                const.CONF_LOG_DRINKS: False,
            }
        }
        hass.states = types.SimpleNamespace(async_all=lambda domain: [])
        hass.auth = types.SimpleNamespace(
            async_get_user=AsyncMock(return_value=None), current_user=None
        )
        hass.async_add_executor_job = AsyncMock()
        await _log_price_change(hass, "user-id", "add_drink", "Bier+1")
        hass.async_add_executor_job.assert_not_called()
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_log_pin_change_logged(tmp_path):
    hass, _write_price_list_log, _log_price_change, _, const, cleanup = _setup_env(tmp_path)
    try:
        hass.data = {const.DOMAIN: {const.CONF_ENABLE_LOGGING: True, const.CONF_LOG_PIN_SET: True}}
        hass.states = types.SimpleNamespace(async_all=lambda domain: [])
        hass.auth = types.SimpleNamespace(async_get_user=AsyncMock(return_value=None), current_user=None)
        hass.async_add_executor_job = AsyncMock()
        await _log_price_change(hass, "user-id", "set_pin", "Alice:set")
        hass.async_add_executor_job.assert_awaited_once()
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_no_log_when_pin_logging_disabled(tmp_path):
    hass, _write_price_list_log, _log_price_change, _, const, cleanup = _setup_env(tmp_path)
    try:
        hass.data = {const.DOMAIN: {const.CONF_ENABLE_LOGGING: True, const.CONF_LOG_PIN_SET: False}}
        hass.states = types.SimpleNamespace(async_all=lambda domain: [])
        hass.auth = types.SimpleNamespace(async_get_user=AsyncMock(return_value=None), current_user=None)
        hass.async_add_executor_job = AsyncMock()
        await _log_price_change(hass, "user-id", "set_pin", "Alice:set")
        hass.async_add_executor_job.assert_not_called()
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_logging_toggle_always_logged(tmp_path):
    hass, _write_price_list_log, _, OptionsFlowHandler, const, cleanup = _setup_env(tmp_path)
    try:
        hass.data = {const.DOMAIN: {}}
        hass.states = types.SimpleNamespace(async_all=lambda domain: [])
        mock_user = types.SimpleNamespace(id="user-1", name="Tester", username="tester")
        hass.auth = types.SimpleNamespace(
            async_get_user=AsyncMock(return_value=mock_user), current_user=mock_user
        )
        flow = OptionsFlowHandler(config_entry=None)
        flow.hass = hass
        flow.context = {}
        flow._enable_logging = False
        flow._log_drinks = True
        flow._log_price_changes = True
        flow._log_free_drinks = True
        flow.async_step_menu = AsyncMock(return_value=None)
        hass.async_add_executor_job = AsyncMock()
        await flow.async_step_logging(
            {
                const.CONF_ENABLE_LOGGING: True,
                const.CONF_LOG_DRINKS: True,
                const.CONF_LOG_PRICE_CHANGES: True,
                const.CONF_LOG_FREE_DRINKS: True,
                const.CONF_LOG_PIN_SET: True,
                const.CONF_LOG_SETTINGS: True,
            }
        )
        hass.async_add_executor_job.assert_awaited_once()
        args = hass.async_add_executor_job.await_args.args
        assert args[0] is _write_price_list_log
        assert args[3] == "enable_logging"
        assert args[4] == "logging"
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_individual_logging_toggle_logged(tmp_path):
    hass, _write_price_list_log, _, OptionsFlowHandler, const, cleanup = _setup_env(tmp_path)
    try:
        hass.data = {const.DOMAIN: {}}
        hass.states = types.SimpleNamespace(async_all=lambda domain: [])
        mock_user = types.SimpleNamespace(id="user-1", name="Tester", username="tester")
        hass.auth = types.SimpleNamespace(
            async_get_user=AsyncMock(return_value=mock_user), current_user=mock_user
        )
        flow = OptionsFlowHandler(config_entry=None)
        flow.hass = hass
        flow.context = {}
        flow._enable_logging = True
        flow._log_drinks = False
        flow._log_price_changes = True
        flow._log_free_drinks = True
        flow.async_step_menu = AsyncMock(return_value=None)
        hass.async_add_executor_job = AsyncMock()
        await flow.async_step_logging(
            {
                const.CONF_ENABLE_LOGGING: True,
                const.CONF_LOG_DRINKS: True,
                const.CONF_LOG_PRICE_CHANGES: True,
                const.CONF_LOG_FREE_DRINKS: True,
                const.CONF_LOG_PIN_SET: True,
                const.CONF_LOG_SETTINGS: True,
            }
        )
        hass.async_add_executor_job.assert_awaited_once()
        args = hass.async_add_executor_job.await_args.args
        assert args[0] is _write_price_list_log
        assert args[3] == "enable_logging"
        assert args[4] == "log_drinks"
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_pin_logging_toggle_logged(tmp_path):
    hass, _write_price_list_log, _, OptionsFlowHandler, const, cleanup = _setup_env(tmp_path)
    try:
        hass.data = {const.DOMAIN: {}}
        hass.states = types.SimpleNamespace(async_all=lambda domain: [])
        mock_user = types.SimpleNamespace(id="user-1", name="Tester", username="tester")
        hass.auth = types.SimpleNamespace(
            async_get_user=AsyncMock(return_value=mock_user), current_user=mock_user
        )
        flow = OptionsFlowHandler(config_entry=None)
        flow.hass = hass
        flow.context = {}
        flow._enable_logging = True
        flow._log_drinks = True
        flow._log_price_changes = True
        flow._log_free_drinks = True
        flow._log_pin_set = False
        flow.async_step_menu = AsyncMock(return_value=None)
        hass.async_add_executor_job = AsyncMock()
        await flow.async_step_logging(
            {
                const.CONF_ENABLE_LOGGING: True,
                const.CONF_LOG_DRINKS: True,
                const.CONF_LOG_PRICE_CHANGES: True,
                const.CONF_LOG_FREE_DRINKS: True,
                const.CONF_LOG_PIN_SET: True,
                const.CONF_LOG_SETTINGS: True,
            }
        )
        hass.async_add_executor_job.assert_awaited_once()
        args = hass.async_add_executor_job.await_args.args
        assert args[0] is _write_price_list_log
        assert args[3] == "enable_logging"
        assert args[4] == "log_pin_set"
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_settings_logging_toggle_logged(tmp_path):
    hass, _write_price_list_log, _, OptionsFlowHandler, const, cleanup = _setup_env(tmp_path)
    try:
        hass.data = {const.DOMAIN: {}}
        hass.states = types.SimpleNamespace(async_all=lambda domain: [])
        mock_user = types.SimpleNamespace(id="user-1", name="Tester", username="tester")
        hass.auth = types.SimpleNamespace(
            async_get_user=AsyncMock(return_value=mock_user), current_user=mock_user
        )
        flow = OptionsFlowHandler(config_entry=None)
        flow.hass = hass
        flow.context = {}
        flow._enable_logging = True
        flow._log_drinks = True
        flow._log_price_changes = True
        flow._log_free_drinks = True
        flow._log_pin_set = True
        flow._log_settings = False
        flow.async_step_menu = AsyncMock(return_value=None)
        hass.async_add_executor_job = AsyncMock()
        await flow.async_step_logging(
            {
                const.CONF_ENABLE_LOGGING: True,
                const.CONF_LOG_DRINKS: True,
                const.CONF_LOG_PRICE_CHANGES: True,
                const.CONF_LOG_FREE_DRINKS: True,
                const.CONF_LOG_PIN_SET: True,
                const.CONF_LOG_SETTINGS: True,
            }
        )
        hass.async_add_executor_job.assert_awaited_once()
        args = hass.async_add_executor_job.await_args.args
        assert args[0] is _write_price_list_log
        assert args[3] == "enable_logging"
        assert args[4] == "log_settings"
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_log_free_drinks_enable(tmp_path):
    hass, _, _, OptionsFlowHandler, const, cleanup = _setup_env(tmp_path)
    try:
        hass.auth = types.SimpleNamespace(current_user=types.SimpleNamespace(id="user-1"))
        flow = OptionsFlowHandler(config_entry=None)
        flow.hass = hass
        flow.context = {}
        flow.async_step_drinks = AsyncMock(return_value=None)
        flow._user_id = "user-1"
        flow._enable_free_drinks = False
        with patch("tally_list.config_flow._log_price_change", AsyncMock()) as log_mock:
            await flow.async_step_free_drinks({const.CONF_ENABLE_FREE_DRINKS: True})
            log_mock.assert_awaited_once_with(
                hass, "user-1", "enable_free_drinks", "False->True"
            )
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_log_free_drinks_disable(tmp_path):
    hass, _, _, OptionsFlowHandler, const, cleanup = _setup_env(tmp_path)
    try:
        hass.auth = types.SimpleNamespace(current_user=types.SimpleNamespace(id="user-1"))
        flow = OptionsFlowHandler(config_entry=None)
        flow.hass = hass
        flow.context = {}
        flow.async_step_drinks = AsyncMock(return_value=None)
        flow.async_show_menu = lambda **kwargs: None
        flow._user_id = "user-1"
        flow._enable_free_drinks = True
        with patch("tally_list.config_flow._log_price_change", AsyncMock()) as log_mock:
            await flow.async_step_free_drinks_confirm({"confirm": "YES I WANT"})
            log_mock.assert_awaited_once_with(
                hass, "user-1", "disable_free_drinks", "True->False"
            )
    finally:
        cleanup()


@pytest.mark.asyncio
async def test_no_log_when_settings_logging_disabled(tmp_path):
    hass, _write_price_list_log, _log_price_change, _, const, cleanup = _setup_env(tmp_path)
    try:
        hass.data = {const.DOMAIN: {const.CONF_ENABLE_LOGGING: True, const.CONF_LOG_SETTINGS: False}}
        hass.states = types.SimpleNamespace(async_all=lambda domain: [])
        hass.auth = types.SimpleNamespace(async_get_user=AsyncMock(return_value=None), current_user=None)
        hass.async_add_executor_job = AsyncMock()
        await _log_price_change(hass, "user-id", "exclude_user", "Alice")
        hass.async_add_executor_job.assert_not_called()
    finally:
        cleanup()
