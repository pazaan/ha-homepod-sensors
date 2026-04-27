# Switch-Pulse Trigger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the iOS time-of-day Shortcut trigger with an integration-owned switch entity that pulses on a configurable interval, enabling Apple TV Home Hub support.

**Architecture:** A new `switch` platform exposes a single switch entity per integration instance. The coordinator owns a `pulse()` method that turns the switch on and schedules a turn-off after a fixed 2-second window via `async_call_later`. The `__init__.py` setup hook registers an `async_track_time_interval` listener that drives `pulse()` on every interval tick, plus an immediate cold-start pulse so first-install flows populate quickly. The webhook ingestion path is untouched.

**Tech Stack:** Home Assistant 2024.1+, `pytest-homeassistant-custom-component`, asyncio, no new third-party deps.

**Spec:** [docs/superpowers/specs/2026-04-27-switch-pulse-trigger-design.md](../specs/2026-04-27-switch-pulse-trigger-design.md)

---

## File Structure

**Create:**
- `custom_components/homepod_sensors/switch.py` — switch platform (`HomePodRefreshSwitch`).
- `tests/test_coordinator.py` — coordinator pulse and shutdown logic tests.
- `tests/test_switch.py` — switch entity behavior tests.

**Modify:**
- `custom_components/homepod_sensors/manifest.json` — bump version to `2.0.0`.
- `custom_components/homepod_sensors/const.py` — add `PULSE_DURATION_SECONDS`, add `"switch"` to `PLATFORMS`.
- `custom_components/homepod_sensors/coordinator.py` — add `pulse()`, `register_switch()`, `async_shutdown()`, and the `_pulse_off_unsub` field.
- `custom_components/homepod_sensors/__init__.py` — forward switch platform, register interval listener, fire immediate pulse, re-register listener on options change, cancel listener and shutdown coordinator on unload.
- `custom_components/homepod_sensors/translations/en.json` — add switch entity name.
- `tests/test_init.py` — fix incorrect `my_integration` import (existing bug — file currently references the wrong module), add coverage for new behaviors.
- `README.md` — rewrite Step 2, add HomeKit Bridge prerequisite, add HTTPS guidance, add "Upgrading from 1.x".
- `shortcuts/README.md` — rewrite trigger section.

---

## Task 1: Bump version and add constants

**Files:**
- Modify: `custom_components/homepod_sensors/manifest.json`
- Modify: `custom_components/homepod_sensors/const.py`

- [ ] **Step 1: Bump manifest version**

Replace `"version": "1.0.0"` with `"version": "2.0.0"` in `manifest.json`.

- [ ] **Step 2: Add `PULSE_DURATION_SECONDS`**

Add a new constant in `const.py` so downstream tasks can reference it. The bottom of the file becomes:

```python
DEFAULT_UPDATE_INTERVAL = 5  # minutes
DEFAULT_STALENESS_MULTIPLIER = 3  # stale after 3x the update interval
PULSE_DURATION_SECONDS = 2  # how long the refresh switch stays "on" per pulse

PLATFORMS = ["sensor", "binary_sensor"]
```

Note: `"switch"` is intentionally **not** added to `PLATFORMS` here. It is added in Task 3 once `switch.py` exists. Adding it earlier would break `async_setup_entry` because HA tries to import each listed platform module.

- [ ] **Step 3: Verify lint passes**

Run: `ruff check custom_components/homepod_sensors/`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add custom_components/homepod_sensors/manifest.json custom_components/homepod_sensors/const.py
git commit -m "chore: bump to 2.0.0, add pulse constants"
```

---

## Task 2: Coordinator pulse logic (TDD)

**Files:**
- Modify: `custom_components/homepod_sensors/coordinator.py`
- Create: `tests/test_coordinator.py`

- [ ] **Step 1: Write failing tests for `register_switch`, `pulse`, and `async_shutdown`**

Create `tests/test_coordinator.py`:

```python
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

    coordinator.async_shutdown()
    assert coordinator._pulse_off_unsub is None
```

- [ ] **Step 2: Run tests — expect failures**

Run: `pytest tests/test_coordinator.py -v`
Expected: FAIL with `AttributeError: 'HomePodCoordinator' object has no attribute 'pulse'` (or similar).

- [ ] **Step 3: Implement coordinator changes**

Replace `custom_components/homepod_sensors/coordinator.py` with:

```python
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
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/test_coordinator.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run: `pytest tests/ -v`
Expected: existing webhook + sensor tests still pass.

- [ ] **Step 6: Commit**

```bash
git add custom_components/homepod_sensors/coordinator.py tests/test_coordinator.py
git commit -m "feat(coordinator): add pulse() and async_shutdown()"
```

---

## Task 3: Switch entity (TDD)

**Files:**
- Create: `custom_components/homepod_sensors/switch.py`
- Create: `tests/test_switch.py`
- Modify: `custom_components/homepod_sensors/const.py` (add `"switch"` to `PLATFORMS`)

- [ ] **Step 1: Write failing switch entity tests**

Create `tests/test_switch.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/test_switch.py -v`
Expected: FAIL — switch entity not registered (platform missing).

- [ ] **Step 3: Implement `switch.py`**

Create `custom_components/homepod_sensors/switch.py`:

```python
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
    """Switch that pulses on a configurable interval to trigger an iOS Shortcut."""

    _attr_has_entity_name = True
    _attr_name = "Refresh"
    _attr_should_poll = False

    def __init__(self, coordinator: HomePodCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
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
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._attr_is_on = False
        self.async_write_ha_state()
```

> **Note for the engineer:** This task creates the platform but does not yet wire it into `__init__.py`. Tests in this task will still fail because of that — fix in Task 4. If you prefer, run `pytest tests/test_switch.py -v` again here and confirm it now fails for a *different* reason (no switch entity, because no platform is loaded yet). That confirms the platform itself is syntactically valid.

- [ ] **Step 4: Quick sanity import**

Run: `.venv/bin/python -c "from custom_components.homepod_sensors.switch import HomePodRefreshSwitch"`
Expected: no errors.

- [ ] **Step 5: Add `"switch"` to `PLATFORMS` in `const.py`**

Open `custom_components/homepod_sensors/const.py` and update:

```python
PLATFORMS = ["sensor", "binary_sensor", "switch"]
```

(`PLATFORMS` was deliberately left as `["sensor", "binary_sensor"]` until now — adding the entry before the platform module existed would have broken `async_setup_entry` mid-rebase. With `switch.py` now in place this is safe.)

- [ ] **Step 6: Commit**

```bash
git add custom_components/homepod_sensors/switch.py tests/test_switch.py custom_components/homepod_sensors/const.py
git commit -m "feat(switch): add refresh switch platform"
```

---

## Task 4: Wire switch platform + immediate pulse on setup

**Files:**
- Modify: `custom_components/homepod_sensors/__init__.py`
- Modify: `tests/test_init.py`

- [ ] **Step 1: Fix existing import bug in `tests/test_init.py`**

The current `tests/test_init.py` has a stale template import (`from custom_components.my_integration import DOMAIN`). Replace it now so the file works against this codebase.

Replace the entire contents of `tests/test_init.py` with:

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/test_init.py -v`
Expected: FAIL — switch platform not loaded; no immediate pulse.

- [ ] **Step 3: Update `__init__.py`**

Replace `custom_components/homepod_sensors/__init__.py` with:

```python
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
        coordinator.async_shutdown()

    ha_webhook.async_unregister(hass, entry.data[CONF_WEBHOOK_ID])
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unloaded
```

- [ ] **Step 4: Run tests — expect pass**

Run: `pytest tests/test_init.py tests/test_switch.py -v`
Expected: all pass.

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -v`
Expected: all green (sensor, binary_sensor, webhook, config_flow, coordinator, switch, init).

- [ ] **Step 6: Commit**

```bash
git add custom_components/homepod_sensors/__init__.py tests/test_init.py
git commit -m "feat(init): wire switch platform, interval listener, cold-start pulse"
```

---

## Task 5: Re-register listener on options change (TDD)

**Files:**
- Modify: `tests/test_init.py`

The implementation already lives in `async_update_options` from Task 4. This task adds a regression test that exercises it.

- [ ] **Step 1: Add the test**

Append to `tests/test_init.py`:

```python
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

    coordinator = hass.data["homepod_sensors"][setup_integration.entry_id]
    assert coordinator.update_interval_minutes == 10
```

- [ ] **Step 2: Run test — expect pass**

Run: `pytest tests/test_init.py::test_options_change_reregisters_interval -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_init.py
git commit -m "test(init): cover interval re-registration on options change"
```

---

## Task 6: Translations

**Files:**
- Modify: `custom_components/homepod_sensors/translations/en.json`

- [ ] **Step 1: Add switch entity translation**

Edit `translations/en.json`. Add a `"switch"` block under `"entity"`. The full updated `entity` block:

```json
"entity": {
  "sensor": {
    "temperature": { "name": "Temperature" },
    "humidity": { "name": "Humidity" },
    "last_updated": { "name": "Last Updated" }
  },
  "binary_sensor": {
    "stale": {
      "name": "Stale",
      "state": { "on": "Stale", "off": "Fresh" }
    }
  },
  "switch": {
    "refresh": { "name": "Refresh" }
  }
}
```

- [ ] **Step 2: Validate JSON**

Run: `python -c "import json; json.load(open('custom_components/homepod_sensors/translations/en.json'))"`
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add custom_components/homepod_sensors/translations/en.json
git commit -m "i18n: add refresh switch translation"
```

---

## Task 7: README and shortcuts/README

**Files:**
- Modify: `README.md`
- Modify: `shortcuts/README.md`

- [ ] **Step 1: Replace README Step 2 with the switch-pulse setup**

Find the "### Step 2 — Create the iOS Shortcut" section in `README.md` and replace its body (everything between that heading and "### Step 3 — Verify") with:

```markdown
### Step 2 — Expose the Refresh switch to Apple Home

The integration creates a `switch.homepod_sensors_refresh` entity that pulses on the interval you chose. Apple TV (and any iOS Home Hub) will run the Shortcut whenever this switch turns on.

1. Set up Home Assistant's [HomeKit Bridge integration](https://www.home-assistant.io/integrations/homekit/) if you haven't already.
2. Add `switch.homepod_sensors_refresh` to its `include_entities` list (UI: *Settings → Devices & Services → HomeKit Bridge → Configure → Entities*).
3. Open the **Home** app on your iPhone and confirm the switch appears as an accessory.

### Step 3 — Create the iOS Shortcut

**Option A: Import the template (easiest)**

Download [`shortcuts/HomePod Sensors.shortcut`](shortcuts/HomePod%20Sensors.shortcut) on your iPhone and open it. When prompted, paste your webhook URL. Done.

**Option B: Create manually**

1. Open the **Shortcuts** app on your iPhone.
2. Build the data-collection actions (see [shortcuts/README.md](shortcuts/README.md) for the full action list).
3. End the Shortcut with a **Get Contents of URL** action that POSTs the JSON payload to your webhook URL.

### Step 4 — Create the Apple TV automation

In the **Home** app on your iPhone:

1. Tap **Automation → +**.
2. Trigger: **An Accessory Is Controlled** → select **HomePod Sensors Refresh** → **Turns On**.
3. Action: **Run Shortcut** → select your HomePod Sensors shortcut.
4. Confirm "Run At Home Hub" is shown — this is what makes Apple TV execute it.
5. Save and enable.
```

Then renumber the existing "### Step 3 — Verify" section to "### Step 5 — Verify".

- [ ] **Step 2: Add HTTPS guidance after the new Step 4**

Add a new section between Step 4 and Step 5:

```markdown
### Transport security

The webhook URL contains a long-lived token in its path. **Do not POST over plain HTTP on a network you don't fully trust** — anyone on the same Wi-Fi can sniff the token and the sensor data, and (with the token) can spoof readings.

Recommended local-HTTPS options:

- A reverse proxy (Caddy, NGINX, Traefik) terminating TLS with a Let's Encrypt certificate via DNS-01 challenge.
- Tailscale or WireGuard between the iOS device and HA.
- HA core HTTPS configured with `ssl_certificate` / `ssl_key`.

Nabu Casa's remote URL also works but routes traffic over the internet — overkill for an integration whose entire premise is a local push.
```

- [ ] **Step 3: Add "Upgrading from 1.x" section before "## Version History"**

Insert this section:

```markdown
## Upgrading from 1.x

Version 2.0 changes the Shortcut trigger from "Time of Day" to "Accessory Turns On". Your webhook URL and existing HA configuration carry over — only the iOS automation needs to be rebuilt:

1. Update the integration via HACS and restart Home Assistant.
2. Open the **Home** app and add `switch.homepod_sensors_refresh` to your HomeKit Bridge include list (see Step 2 above).
3. Delete your old "Time of Day" automation in the **Shortcuts** app.
4. Create the new automation in the **Home** app (see Step 4 above).

Apple TV users gain support — the v1.x time-based trigger never worked on Apple TV Home Hubs.
```

- [ ] **Step 4: Update the Version History table**

Add a row above the existing 1.0.0 row:

```markdown
| 2.0.0 | Replaces time-of-day Shortcut trigger with an integration-owned switch entity. Adds Apple TV Home Hub support. **Breaking:** existing users must rebuild their iOS automation — see *Upgrading from 1.x*. |
```

- [ ] **Step 5: Rewrite shortcuts/README.md trigger section**

In `shortcuts/README.md`, replace the "## Automation Setup" section with:

```markdown
## Automation Setup

The integration's switch entity is the trigger. Once it is exposed via HomeKit Bridge, set up an automation in the iPhone **Home** app:

1. Open **Home → Automation → +**.
2. Trigger: **An Accessory Is Controlled** → **HomePod Sensors Refresh** → **Turns On**.
3. Action: **Run Shortcut** → select *HomePod Sensors*.
4. Confirm the Home Hub badge ("Run At Home Hub") appears, then save.

The integration sets the switch *off* automatically a couple of seconds after each pulse, so the next interval gets a fresh "turns on" edge.
```

- [ ] **Step 6: Commit**

```bash
git add README.md shortcuts/README.md
git commit -m "docs: rewrite for switch-pulse trigger and HomeKit setup"
```

---

## Task 8: Final regression sweep

- [ ] **Step 1: Run the full test suite**

Run: `pytest tests/ -v`
Expected: all tests pass.

- [ ] **Step 2: Lint**

Run: `ruff check custom_components/ tests/`
Expected: no errors.

- [ ] **Step 3: Manifest sanity**

Run: `python -c "import json; m = json.load(open('custom_components/homepod_sensors/manifest.json')); assert m['version'] == '2.0.0'; assert 'webhook' in m['dependencies']"`
Expected: no output.

- [ ] **Step 4: Confirm no stray TODO/placeholder strings**

Run: `grep -rn -E '(TODO|FIXME|XXX)' custom_components/ tests/ docs/superpowers/`
Expected: no matches in the new code (any pre-existing matches in docs are out of scope).

- [ ] **Step 5: Done — no commit, just verify clean state**

Run: `git status`
Expected: working tree clean.

---

## Notes for the engineer

- **Why `async_call_later` and not `asyncio.sleep` + `Task`:** `async_call_later` integrates with HA's event loop clock, so tests can advance time deterministically with `async_fire_time_changed`. A raw `asyncio.sleep` would force tests to either sleep in real time or monkey-patch asyncio.
- **Why a synthetic "Bridge" device for the switch:** keeping the switch on its own device prevents it from cluttering each HomePod's device card. The HomePod devices are pure-data accessories; the switch is integration plumbing.
- **Why no immediate pulse on options change:** the user is just adjusting cadence, not asking for a refresh. The next tick will fire within the new interval. Firing on every options-flow save would also create noisy edges if the user toggles between a few values.
- **`INTERVAL_UNSUBS` is module-level:** simpler than threading the unsub through the coordinator, and isolates the time-listener concern from the data coordinator. Keyed by `entry.entry_id` to support reload-without-restart cleanly.
