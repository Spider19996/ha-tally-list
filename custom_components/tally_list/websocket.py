"""WebSocket commands for Tally List."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.components import websocket_api
from homeassistant.exceptions import Unauthorized
import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_OVERRIDE_USERS,
    CONF_PUBLIC_DEVICES,
    CONF_USER_PINS,
)


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


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/is_public_device"})
@websocket_api.async_response
async def websocket_is_public_device(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Return whether the connected user is configured as public device."""
    if connection.user is None:
        raise Unauthorized

    person_name: str | None = None
    for state in hass.states.async_all("person"):
        if state.attributes.get("user_id") == connection.user.id:
            person_name = state.name
            break

    public_devices = hass.data.get(DOMAIN, {}).get(CONF_PUBLIC_DEVICES, [])
    connection.send_result(msg["id"], {"is_public": person_name in public_devices})


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/login",
        vol.Required("user"): str,
        vol.Required("pin"): str,
    }
)
@websocket_api.async_response
async def websocket_login(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Validate a user's PIN and create a login session."""
    if connection.user is None:
        raise Unauthorized

    user_pins = hass.data.get(DOMAIN, {}).get(CONF_USER_PINS, {})
    sessions = hass.data.setdefault(DOMAIN, {}).setdefault("sessions", {})

    pin = str(msg["pin"])
    user = msg["user"]
    success = user_pins.get(user) == pin

    if success:
        sessions[connection.user.id] = user

    connection.send_result(msg["id"], {"success": success})


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/logout"})
@websocket_api.async_response
async def websocket_logout(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict,
) -> None:
    """Clear a previously created login session."""
    if connection.user is None:
        raise Unauthorized

    sessions = hass.data.get(DOMAIN, {}).get("sessions", {})
    sessions.pop(connection.user.id, None)

    connection.send_result(msg["id"], {"success": True})


async def async_register(hass: HomeAssistant) -> None:
    """Register Tally List WebSocket commands."""
    websocket_api.async_register_command(hass, websocket_get_admins)
    websocket_api.async_register_command(hass, websocket_is_public_device)
    websocket_api.async_register_command(hass, websocket_login)
    websocket_api.async_register_command(hass, websocket_logout)
