"""Serve the Lovelace cards bundled with this integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

from .const import CARD_FILENAME, CARD_URL_BASE, DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the card and register it as a Lovelace resource."""
    card_path = str(Path(__file__).parent / "www" / CARD_FILENAME)

    # Serve the card file under /tally_list/. The fallback covers Home
    # Assistant versions without async_register_static_paths (< 2024.6).
    if hasattr(hass.http, "async_register_static_paths"):
        from homeassistant.components.http import StaticPathConfig

        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_BASE, card_path, cache_headers=False)]
        )
    else:  # pragma: no cover - legacy Home Assistant
        hass.http.register_static_path(CARD_URL_BASE, card_path, cache_headers=False)

    version: str | None = None
    try:
        from homeassistant.loader import async_get_integration

        integration = await async_get_integration(hass, DOMAIN)
        version = integration.version
    except Exception:  # noqa: BLE001 - version is only used for cache busting
        _LOGGER.debug("Could not determine integration version", exc_info=True)

    url = f"{CARD_URL_BASE}?v={version}" if version else CARD_URL_BASE
    await _async_register_resource(hass, url)


async def _async_register_resource(hass: HomeAssistant, url: str) -> None:
    """Register or update the card as a Lovelace resource."""
    lovelace_data = hass.data.get("lovelace") or {}
    resources = lovelace_data.get("resources")
    if resources is None:
        _LOGGER.debug("Lovelace resources not available; skipping registration")
        return

    try:
        items = (
            list(resources.async_items())
            if hasattr(resources, "async_items")
            else []
        )
        for item in items:
            item_url = str(item.get("url", ""))
            if item_url.split("?")[0] != CARD_URL_BASE:
                continue
            # Already registered: only update the URL when the version changed.
            if item_url != url and item.get("id") is not None:
                await resources.async_update_item(item["id"], {"url": url})
            return

        if not hasattr(resources, "async_create_item"):
            # YAML mode: the collection is read-only, users add resources manually.
            _LOGGER.info(
                "Lovelace runs in YAML mode; add the Tally List card manually:\n"
                "lovelace:\n  resources:\n    - url: %s\n      type: module",
                CARD_URL_BASE,
            )
            return

        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.info("Registered %s as a Lovelace resource", url)
    except Exception:  # noqa: BLE001 - card registration must never break setup
        _LOGGER.exception(
            "Failed to register the Tally List card as a Lovelace resource"
        )