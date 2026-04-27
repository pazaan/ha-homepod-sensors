"""HomePod Sensors integration for Home Assistant."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components import webhook as ha_webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_UPDATE_INTERVAL,
    CONF_WEBHOOK_ID,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import HomePodCoordinator
from .webhook import async_handle_webhook

_LOGGER = logging.getLogger(__name__)

# Per-entry runtime state we manage outside the coordinator.
INTERVAL_UNSUBS: dict[str, CALLBACK_TYPE] = {}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HomePod Sensors from a config entry."""
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator = HomePodCoordinator(hass, update_interval_minutes=update_interval)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    webhook_id = entry.data[CONF_WEBHOOK_ID]
    ha_webhook.async_register(
        hass,
        DOMAIN,
        "HomePod Sensors",
        webhook_id,
        async_handle_webhook,
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _on_tick(_now) -> None:
        await coordinator.pulse()

    INTERVAL_UNSUBS[entry.entry_id] = async_track_time_interval(
        hass, _on_tick, timedelta(minutes=update_interval)
    )

    # Cold-start pulse so sensors populate as soon as the user finishes Shortcut setup.
    await coordinator.pulse()

    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Re-register the interval listener when the user changes the update interval."""
    coordinator: HomePodCoordinator = hass.data[DOMAIN][entry.entry_id]
    new_interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    coordinator.update_interval_minutes = new_interval

    old_unsub = INTERVAL_UNSUBS.pop(entry.entry_id, None)
    if old_unsub is not None:
        old_unsub()

    async def _on_tick(_now) -> None:
        await coordinator.pulse()

    INTERVAL_UNSUBS[entry.entry_id] = async_track_time_interval(
        hass, _on_tick, timedelta(minutes=new_interval)
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unsub = INTERVAL_UNSUBS.pop(entry.entry_id, None)
    if unsub is not None:
        unsub()

    coordinator: HomePodCoordinator | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is not None:
        await coordinator.async_shutdown()

    ha_webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
