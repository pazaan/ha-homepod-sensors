"""Tests for HomePodCoordinator pulse logic."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.homepod_sensors.const import (
    DEFAULT_UPDATE_INTERVAL,
    PULSE_DURATION_SECONDS,
)
from custom_components.homepod_sensors.coordinator import HomePodCoordinator


@pytest.fixture
def coordinator(hass: HomeAssistant) -> HomePodCoordinator:
    return HomePodCoordinator(hass, update_interval_minutes=DEFAULT_UPDATE_INTERVAL)


async def test_pulse_no_op_without_switch(coordinator: HomePodCoordinator) -> None:
    """pulse() must not raise when no switch is registered."""
    await coordinator.pulse()
    assert coordinator._pulse_off_unsub is None


async def test_pulse_turns_switch_on_then_off(
    hass: HomeAssistant, coordinator: HomePodCoordinator
) -> None:
    """pulse() turns switch on immediately, schedules turn-off."""
    switch = MagicMock()
    switch.async_turn_on = AsyncMock()
    switch.async_turn_off = AsyncMock()
    coordinator.register_switch(switch)

    await coordinator.pulse()
    assert switch.async_turn_on.await_count == 1
    assert switch.async_turn_off.await_count == 0
    assert coordinator._pulse_off_unsub is not None

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=PULSE_DURATION_SECONDS + 1)
    )
    await hass.async_block_till_done()

    assert switch.async_turn_off.await_count == 1
    assert coordinator._pulse_off_unsub is None


async def test_rapid_pulse_cancels_previous_off(
    hass: HomeAssistant, coordinator: HomePodCoordinator
) -> None:
    """Calling pulse() while a pulse is in flight cancels the prior off-timer."""
    switch = MagicMock()
    switch.async_turn_on = AsyncMock()
    switch.async_turn_off = AsyncMock()
    coordinator.register_switch(switch)

    await coordinator.pulse()
    first_unsub = coordinator._pulse_off_unsub
    assert first_unsub is not None

    await coordinator.pulse()
    second_unsub = coordinator._pulse_off_unsub
    assert second_unsub is not None
    assert second_unsub is not first_unsub

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=PULSE_DURATION_SECONDS + 1)
    )
    await hass.async_block_till_done()

    # Only one turn-off should have fired (the second-scheduled one).
    assert switch.async_turn_off.await_count == 1


async def test_async_shutdown_cancels_in_flight_off(
    coordinator: HomePodCoordinator,
) -> None:
    """async_shutdown() cancels any pending turn-off."""
    switch = MagicMock()
    switch.async_turn_on = AsyncMock()
    switch.async_turn_off = AsyncMock()
    coordinator.register_switch(switch)

    await coordinator.pulse()
    assert coordinator._pulse_off_unsub is not None

    await coordinator.async_shutdown()
    assert coordinator._pulse_off_unsub is None


async def test_pulse_turn_on_failure_leaves_no_dangling_unsub(
    coordinator: HomePodCoordinator,
) -> None:
    """If async_turn_on raises, the prior unsub must already be cleared."""
    switch = MagicMock()
    switch.async_turn_on = AsyncMock()
    switch.async_turn_off = AsyncMock()
    coordinator.register_switch(switch)

    # First pulse establishes a real unsub; capture it so we can cancel it later.
    await coordinator.pulse()
    real_unsub = coordinator._pulse_off_unsub
    assert real_unsub is not None

    # Replace with a stand-in so we can assert it gets called on the next pulse.
    prior_unsub = MagicMock()
    coordinator._pulse_off_unsub = prior_unsub

    # Make the next turn_on raise.
    switch.async_turn_on.side_effect = RuntimeError("entity removed")

    with pytest.raises(RuntimeError):
        await coordinator.pulse()

    # Prior unsub must have been cancelled before the raise.
    assert prior_unsub.call_count == 1

    # Cancel the real timer from the first pulse to avoid a lingering timer.
    real_unsub()
