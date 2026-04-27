"""Tests for HomePod Sensors refresh switch."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.homepod_sensors.const import (
    DOMAIN,
    PULSE_DURATION_SECONDS,
)


@pytest.fixture
async def setup_integration(hass: HomeAssistant, mock_config_entry: MockConfigEntry):
    mock_config_entry.add_to_hass(hass)
    with patch("homeassistant.components.webhook.async_register"), patch(
        "homeassistant.components.webhook.async_unregister"
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()
    return hass.data[DOMAIN][mock_config_entry.entry_id]


async def test_switch_entity_created_on_setup(
    hass: HomeAssistant, setup_integration
) -> None:
    """The integration should expose exactly one refresh switch."""
    state = hass.states.get("switch.homepod_sensors_refresh")
    assert state is not None


async def test_pulse_drives_switch_state(
    hass: HomeAssistant, setup_integration
) -> None:
    """coordinator.pulse() should drive the switch from off → on → off."""
    # Setup fires an immediate pulse — switch should already be on.
    state = hass.states.get("switch.homepod_sensors_refresh")
    assert state.state == "on"

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=PULSE_DURATION_SECONDS + 1)
    )
    await hass.async_block_till_done()

    state = hass.states.get("switch.homepod_sensors_refresh")
    assert state.state == "off"


async def test_manual_toggle(hass: HomeAssistant, setup_integration) -> None:
    """User-initiated turn_on / turn_off should update state without invoking pulse."""
    # Wait for the cold-start pulse to settle.
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=PULSE_DURATION_SECONDS + 1)
    )
    await hass.async_block_till_done()
    assert hass.states.get("switch.homepod_sensors_refresh").state == "off"

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": "switch.homepod_sensors_refresh"},
        blocking=True,
    )
    assert hass.states.get("switch.homepod_sensors_refresh").state == "on"

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": "switch.homepod_sensors_refresh"},
        blocking=True,
    )
    assert hass.states.get("switch.homepod_sensors_refresh").state == "off"
