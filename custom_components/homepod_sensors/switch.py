"""Switch platform for HomePod Sensors integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_WEBHOOK_ID, DOMAIN
from .coordinator import HomePodCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the refresh switch."""
    coordinator: HomePodCoordinator = hass.data[DOMAIN][entry.entry_id]
    switch = HomePodRefreshSwitch(coordinator, entry)
    coordinator.register_switch(switch)
    async_add_entities([switch])


class HomePodRefreshSwitch(SwitchEntity):
    """Switch that pulses on a configurable interval to trigger an iOS Shortcut.

    State is driven both by the coordinator (during pulses) and by the user
    (via the UI). The coordinator only calls async_turn_on/off after the
    platform's async_setup_entry has completed, so the entity is guaranteed
    to be added to HA before any state write.
    """

    _attr_has_entity_name = True
    _attr_name = "Refresh"
    _attr_should_poll = False

    def __init__(self, coordinator: HomePodCoordinator, entry: ConfigEntry) -> None:
        # Coordinator is registered with us via coordinator.register_switch()
        # in the platform setup; this entity does not call back into it.
        webhook_id = entry.data[CONF_WEBHOOK_ID]
        self._attr_unique_id = f"{webhook_id}_refresh_trigger"
        self._attr_is_on = False
        # Device name "HomePod Sensors" + entity name "Refresh" yields the
        # entity_id switch.homepod_sensors_refresh that downstream docs and
        # automation examples rely on. The `_bridge` identifier suffix is
        # internal — keeps this synthetic device distinct from per-HomePod
        # devices, which use the raw serial as their identifier.
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{webhook_id}_bridge")},
            name="HomePod Sensors",
            manufacturer="HomePod Sensors integration",
            model="Refresh trigger",
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on. Called by the coordinator during a pulse cycle, or by the user via the UI."""
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off. Called by the coordinator at the end of a pulse cycle, or by the user via the UI."""
        self._attr_is_on = False
        self.async_write_ha_state()
