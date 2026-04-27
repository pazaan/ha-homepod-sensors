"""Data coordinator for HomePod Sensors integration."""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN, PULSE_DURATION_SECONDS

if TYPE_CHECKING:
    from .switch import HomePodRefreshSwitch

_LOGGER = logging.getLogger(__name__)


class HomePodDeviceData:
    """Holds the latest data for a single HomePod Mini."""

    def __init__(self, serial: str, name: str) -> None:
        self.serial = serial
        self.name = name
        self.temperature_c: float | None = None
        self.humidity_pct: float | None = None
        self.last_seen: datetime | None = None

    def update(self, temperature_c: float, humidity_pct: float) -> None:
        self.temperature_c = temperature_c
        self.humidity_pct = humidity_pct
        self.last_seen = datetime.now(UTC)


class HomePodCoordinator(DataUpdateCoordinator[dict[str, HomePodDeviceData]]):
    """Coordinator that receives push data from iOS Shortcuts webhook."""

    def __init__(self, hass: HomeAssistant, update_interval_minutes: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
        )
        self.data: dict[str, HomePodDeviceData] = {}
        self.update_interval_minutes = update_interval_minutes
        self._new_device_callbacks: list[Callable[[str, HomePodDeviceData], None]] = []
        self._switch: "HomePodRefreshSwitch | None" = None
        self._pulse_off_unsub: CALLBACK_TYPE | None = None

    @callback
    def register_new_device_callback(
        self, cb: Callable[[str, HomePodDeviceData], None]
    ) -> None:
        """Register a callback invoked when a previously-unseen device reports in."""
        self._new_device_callbacks.append(cb)

    @callback
    def register_switch(self, switch: "HomePodRefreshSwitch") -> None:
        """Register the refresh switch so pulse() can drive it."""
        self._switch = switch

    async def pulse(self) -> None:
        """Turn the refresh switch on, schedule it back off after PULSE_DURATION_SECONDS."""
        if self._switch is None:
            return

        if self._pulse_off_unsub is not None:
            self._pulse_off_unsub()
            self._pulse_off_unsub = None

        await self._switch.async_turn_on()

        async def _turn_off(_now: datetime) -> None:
            self._pulse_off_unsub = None
            if self._switch is not None:
                await self._switch.async_turn_off()

        self._pulse_off_unsub = async_call_later(
            self.hass, timedelta(seconds=PULSE_DURATION_SECONDS), _turn_off
        )

    @callback
    def async_shutdown(self) -> None:
        """Cancel any pending pulse-off on unload."""
        if self._pulse_off_unsub is not None:
            self._pulse_off_unsub()
            self._pulse_off_unsub = None

    def handle_webhook_payload(self, devices: list[dict]) -> None:
        """Process incoming payload from the iOS Shortcut."""
        new_serials: list[str] = []

        for device in devices:
            serial = device.get("serial", "").strip()
            name = device.get("name", f"HomePod {serial[:6]}").strip()
            temp = device.get("temperature_c")
            humidity = device.get("humidity_pct")

            if not serial or temp is None or humidity is None:
                _LOGGER.warning("Skipping malformed device payload: %s", device)
                continue

            is_new = serial not in self.data
            if is_new:
                self.data[serial] = HomePodDeviceData(serial=serial, name=name)
                new_serials.append(serial)

            self.data[serial].update(float(temp), float(humidity))

        self.async_set_updated_data(self.data)

        for serial in new_serials:
            for cb in self._new_device_callbacks:
                cb(serial, self.data[serial])

    async def _async_update_data(self) -> dict[str, HomePodDeviceData]:
        """Not used — data arrives via webhook push only."""
        return self.data
