"""WebSocket commands for Tally List."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.components import websocket_api
from homeassistant.exceptions import Unauthorized
import voluptuous as vol

from .const import DOMAIN, CONF_OVERRIDE_USERS


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_admins"})
@websocket_api.async_response
async def websocket_get_admins(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return a list of admin user names."""
    if connection.user is None:
        raise Unauthorized

    admins = hass.data.get(DOMAIN, {}).get(CONF_OVERRIDE_USERS, [])
    connection.send_result(msg["id"], {"admins": admins})


async def async_register(hass: HomeAssistant) -> None:
    """Register Tally List WebSocket commands."""
    websocket_api.async_register_command(hass, websocket_get_admins)
