from pathlib import Path
import sys
import types
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
import importlib.machinery
from importlib import import_module
from unittest.mock import AsyncMock, patch


def _setup_env(tmp_path):
    original = set(sys.modules.keys())

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
    util_dt_mod = types.ModuleType("homeassistant.util.dt")
    util_dt_mod.get_time_zone = ZoneInfo
    util_dt_mod.now = datetime.now
    util_mod.dt = util_dt_mod
    config_entries_mod = types.ModuleType("homeassistant.config_entries")

    class ConfigFlow:  # pragma: no cover - simple stub
        def __init_subclass__(cls, **kwargs):
            pass

    class OptionsFlow:  # pragma: no cover - simple stub
        def __init_subclass__(cls, **kwargs):
            pass

    config_entries_mod.ConfigFlow = ConfigFlow
    config_entries_mod.OptionsFlow = OptionsFlow
    core_mod = types.ModuleType("homeassistant.core")

    def callback(func):  # pragma: no cover - simple stub
        return func

    core_mod.callback = callback
    vol_mod = types.ModuleType("voluptuous")

    def _identity(v):  # pragma: no cover - simple stub
        return v

    vol_mod.Schema = _identity
    vol_mod.Required = lambda key, default=None: key
    vol_mod.Optional = lambda key, default=None: key
    vol_mod.Coerce = _identity
    vol_mod.In = _identity
    sys.modules.update(
        {
            "homeassistant": ha,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.entity_registry": er_mod,
            "homeassistant.helpers.selector": selector_mod,
            "homeassistant.util": util_mod,
            "homeassistant.util.dt": util_dt_mod,
            "homeassistant.config_entries": config_entries_mod,
            "homeassistant.core": core_mod,
            "voluptuous": vol_mod,
        }
    )

    component_path = (
        Path(__file__).resolve().parents[1] / "custom_components" / "tally_list"
    )
    sys.path.append(str(component_path.parent))
    pkg = types.ModuleType("tally_list")
    pkg.__path__ = [str(component_path)]
    pkg.__spec__ = importlib.machinery.ModuleSpec(
        name="tally_list", loader=None, is_package=True
    )
    sys.modules["tally_list"] = pkg
    sensor_stub = types.ModuleType("tally_list.sensor")

    class PriceListFeedSensor:  # pragma: no cover - simple stub
        pass

    sensor_stub.PriceListFeedSensor = PriceListFeedSensor
    sys.modules["tally_list.sensor"] = sensor_stub

    config_flow = import_module("tally_list.config_flow")

    def cleanup():
        sys.path.remove(str(component_path.parent))
        for mod in set(sys.modules.keys()) - original:
            del sys.modules[mod]

    return config_flow, cleanup


def test_edit_price_logs_user_and_ignores_no_change(tmp_path):
    config_flow, cleanup = _setup_env(tmp_path)
    try:
        DOMAIN = config_flow.DOMAIN
        CONF_DRINK = config_flow.CONF_DRINK
        CONF_PRICE = config_flow.CONF_PRICE
        CONF_ICON = config_flow.CONF_ICON
        CONF_EXCLUDED_USERS = config_flow.CONF_EXCLUDED_USERS
        CONF_OVERRIDE_USERS = config_flow.CONF_OVERRIDE_USERS
        CONF_PUBLIC_DEVICES = config_flow.CONF_PUBLIC_DEVICES
        CONF_CURRENCY = config_flow.CONF_CURRENCY
        CONF_ENABLE_FREE_DRINKS = config_flow.CONF_ENABLE_FREE_DRINKS

        class DummyConfig:
            def __init__(self, base_path):
                self._base_path = base_path
                self.language = None

            def path(self, *parts):
                return str(Path(self._base_path, *parts))

        class DummyUser:
            def __init__(self, user_id, name):
                self.id = user_id
                self.name = name

        class DummyAuth:
            def __init__(self, user):
                self.current_user = user

            async def async_get_user(self, user_id):  # pragma: no cover - simple stub
                return self.current_user if user_id == self.current_user.id else None

        class DummyHass:
            def __init__(self, base_path):
                self.config = DummyConfig(base_path)
                user = DummyUser("user123", "Tester")
                self.auth = DummyAuth(user)
                self.data = {
                    DOMAIN: {
                        "drinks": {"Bier": 1.6},
                        "drink_icons": {"Bier": "mdi:beer"},
                        "free_amount": 0.0,
                        CONF_EXCLUDED_USERS: [],
                        CONF_OVERRIDE_USERS: [],
                        CONF_PUBLIC_DEVICES: [],
                        CONF_CURRENCY: "€",
                        CONF_ENABLE_FREE_DRINKS: False,
                    }
                }
                self.states = types.SimpleNamespace(async_all=lambda domain=None: [])

        hass = DummyHass(tmp_path)
        flow = config_flow.TallyListOptionsFlowHandler(object())
        flow.hass = hass
        flow.context = {}

        async def dummy_menu(user_input=None):  # pragma: no cover - simple stub
            return None

        flow.async_step_menu = dummy_menu

        async def _run():
            await flow.async_step_init()
            assert flow._user_id == "user123"
            flow._edit_drink = "Bier"
            with patch(
                "tally_list.config_flow._log_price_change", new=AsyncMock()
            ) as log_mock:
                await flow.async_step_edit_price(
                    {CONF_PRICE: 1.7, CONF_ICON: "mdi:beer"}
                )
                log_mock.assert_awaited_once_with(
                    hass, "user123", "edit_drink", "Bier:1.6->1.7"
                )
            flow._edit_drink = "Bier"
            with patch(
                "tally_list.config_flow._log_price_change", new=AsyncMock()
            ) as log_mock:
                await flow.async_step_edit_price(
                    {CONF_PRICE: 1.7, CONF_ICON: "mdi:beer"}
                )
                log_mock.assert_not_called()

        asyncio.run(_run())
    finally:
        cleanup()

