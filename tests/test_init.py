"""Tests for homepod_sensors setup."""
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
    return mock_config_entry


async def test_setup_entry_registers_switch(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Setup must register the refresh switch entity."""
    assert DOMAIN in hass.data
    assert setup_integration.entry_id in hass.data[DOMAIN]
    assert hass.states.get("switch.homepod_sensors_refresh") is not None


async def test_setup_fires_immediate_pulse(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Setup should fire one cold-start pulse so sensors populate quickly."""
    state = hass.states.get("switch.homepod_sensors_refresh")
    assert state.state == "on"

    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=PULSE_DURATION_SECONDS + 1)
    )
    await hass.async_block_till_done()
    assert hass.states.get("switch.homepod_sensors_refresh").state == "off"


async def test_unload_entry(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Unloading should remove the integration's data and unregister the webhook."""
    # Let cold-start pulse settle.
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=PULSE_DURATION_SECONDS + 1)
    )
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert setup_integration.entry_id not in hass.data.get(DOMAIN, {})


async def test_options_change_reregisters_interval(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Changing the update interval should swap the interval listener cleanly."""
    from custom_components.homepod_sensors import INTERVAL_UNSUBS

    original_unsub = INTERVAL_UNSUBS[setup_integration.entry_id]

    hass.config_entries.async_update_entry(
        setup_integration,
        options={"update_interval": 10},
    )
    await hass.async_block_till_done()

    new_unsub = INTERVAL_UNSUBS[setup_integration.entry_id]
    assert new_unsub is not original_unsub

    coordinator = hass.data[DOMAIN][setup_integration.entry_id]
    assert coordinator.update_interval_minutes == 10


async def test_unload_pops_interval_unsub(
    hass: HomeAssistant, setup_integration: MockConfigEntry
) -> None:
    """Unloading the entry must remove its INTERVAL_UNSUBS entry to avoid leaking listeners."""
    from custom_components.homepod_sensors import INTERVAL_UNSUBS

    # Sanity: the listener was registered during setup.
    assert setup_integration.entry_id in INTERVAL_UNSUBS

    # Let the cold-start pulse settle so unload doesn't race the off-timer.
    async_fire_time_changed(
        hass, dt_util.utcnow() + timedelta(seconds=PULSE_DURATION_SECONDS + 1)
    )
    await hass.async_block_till_done()

    assert await hass.config_entries.async_unload(setup_integration.entry_id)
    await hass.async_block_till_done()

    assert setup_integration.entry_id not in INTERVAL_UNSUBS
