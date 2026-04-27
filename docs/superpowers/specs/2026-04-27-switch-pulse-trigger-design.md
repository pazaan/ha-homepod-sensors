# Switch-Pulse Trigger — Design

**Status:** Approved (brainstorm)
**Date:** 2026-04-27
**Target version:** 2.0.0 (breaking change for v1.x users)

## Background

The current integration relies on an iOS Shortcut configured with a "Time of Day" automation that POSTs HomePod sensor data to a webhook every 5 minutes. This works on iPhones and iPads but **not on Apple TV Home Hubs**, which do not support time-of-day Shortcut triggers. Apple TV Home Hubs do support "When an accessory state changes" triggers.

Inspiration: <https://medium.com/@federicoimberti/connecting-homepods-temperature-and-humidity-sensors-to-home-assistant-952398a1a2be>

## Goal

Replace the time-of-day trigger with an integration-owned switch entity that pulses on a configurable interval. The pulse is observed by the Apple TV Home Hub via HomeKit, which runs the Shortcut on the rising edge.

This makes the integration work on Apple TV, iPhone, iPad, or any HomeKit Home Hub — switch-pulse is a strict superset of the time-of-day approach.

## Non-Goals

- Backwards compatibility with v1.x time-of-day Shortcut automations. Users must rebuild their automation as part of upgrading.
- Per-HomePod switch granularity. A single Shortcut reads all HomePods in one POST; one switch is sufficient.
- A separate manual-refresh button entity. The user can toggle the switch by hand for the same effect.
- Configurable pulse duration. Hard-coded at 2 seconds.
- Internet-routed transport hardening (HTTPS guidance is a docs-only addition, not a code change).

## Architecture

### Data flow

```
[interval timer in coordinator]
    └─> coordinator.pulse()
         ├─> switch.async_turn_on()
         ├─> sleep(PULSE_DURATION_SECONDS = 2)
         └─> switch.async_turn_off()
              ↓
       [HomeKit Bridge mirrors switch state to Apple Home]
              ↓
       [Apple TV Home Hub: "When 'HomePod Sensors Refresh' turns on, run Shortcut"]
              ↓
       [Shortcut reads sensors → POST to existing webhook]
              ↓
       [existing webhook handler updates coordinator data]
```

Webhook ingestion is unchanged. Only the trigger mechanism changes.

### Components

#### `const.py`

- Add `PULSE_DURATION_SECONDS = 2`.
- Update `PLATFORMS = ["sensor", "binary_sensor", "switch"]`.

#### `coordinator.py`

`HomePodCoordinator` gains pulse responsibility:

- `pulse()` — async method. No-ops if no switch has been registered yet (defensive against early calls or switch-platform setup failure). Otherwise: cancels any in-flight pulse-off, turns the switch on, then schedules `_turn_off` to run after `PULSE_DURATION_SECONDS` via `async_call_later`. Idempotent: calling while a pulse is in progress restarts the off-timer.
- `_pulse_off_unsub: CALLBACK_TYPE | None` — cancel handle for the currently scheduled turn-off. Uses `homeassistant.helpers.event.async_call_later` so tests can advance time via `async_fire_time_changed`.
- `register_switch(switch)` — called by the switch platform during setup so the coordinator can drive it.
- `async_shutdown()` — calls `_pulse_off_unsub()` if set, clears the reference, on unload.

#### `switch.py` (new)

`HomePodRefreshSwitch(SwitchEntity)`:

- Single instance per integration.
- `unique_id = f"{webhook_id}_refresh_trigger"`.
- `_attr_name = "Refresh"`. With `_attr_has_entity_name = True` and the device name "HomePod Sensors" (below), this yields `entity_id = switch.homepod_sensors_refresh` and friendly name "HomePod Sensors Refresh".
- `DeviceInfo` references a synthetic device `(DOMAIN, f"{webhook_id}_bridge")`, name "HomePod Sensors", manufacturer "HomePod Sensors integration", model "Refresh trigger". The `_bridge` identifier suffix is internal-only and disambiguates this synthetic device from per-HomePod devices (which use the raw serial as their identifier).
- `async_turn_on` / `async_turn_off` update `_attr_is_on` and call `async_write_ha_state()`. They do **not** trigger pulse cycles (the pulse is coordinator-driven; the switch is the visible state).
- Manual user toggle via UI is allowed and useful for debugging.

#### `__init__.py`

In `async_setup_entry`:

1. Build coordinator (existing).
2. Forward platform setups for `sensor`, `binary_sensor`, `switch`.
3. Register `async_track_time_interval(hass, _on_tick, timedelta(minutes=interval))`. Store unsub on the entry via `entry.async_on_unload(unsub)`.
4. Fire one immediate pulse via `coordinator.pulse()` to bootstrap (does not wait one full interval).
5. Register webhook (existing).

`_on_tick` calls `coordinator.pulse()`.

In `async_update_options`: when interval changes, cancel the existing time-interval unsub, register a new one with the updated period. Do **not** fire an immediate pulse on options change.

In `async_unload_entry`: existing webhook unregister, plus `coordinator.async_shutdown()` to cancel any in-flight pulse-off.

#### `config_flow.py`

Unchanged. Existing `update_interval` (1–60 minutes) drives both the pulse cadence and the staleness threshold (3× interval).

#### `README.md` and `shortcuts/README.md`

- Step 2 rewritten: replace time-of-day automation instructions with accessory-state-change instructions.
- New prerequisite section: HomeKit Bridge integration must be configured to expose `switch.homepod_sensors_refresh` to Apple Home (`include_entities` in `homekit:` config).
- New "Upgrading from 1.x" section: rebuild your Shortcut automation trigger from "Time of Day" to "When 'HomePod Sensors Refresh' turns on".
- Carry over the security review's transport recommendation: suggest local HTTPS via reverse proxy + Let's Encrypt DNS-01, or Tailscale, for the iOS POST. Plaintext on LAN exposes the webhook token.

## Lifecycle and edge cases

- **Cold start.** Pulse fires immediately on `async_setup_entry`. Sensors populate as soon as the Shortcut is configured and the Apple TV automation is set up.
- **HA restart.** Switch entity recreated in default off state. First pulse fires from setup. No state persistence.
- **Interval change at runtime.** Old time-interval unsub cancelled, new one registered. No immediate pulse.
- **Rapid pulse calls** (e.g. user toggles switch manually mid-pulse). The coordinator's `_pulse_task` cancellation logic restarts the off-timer cleanly.
- **Manual user toggle.** Works as a trigger. If the user holds the switch on, the next scheduled pulse will still try to turn-on (no-op) and turn-off (which the user may consider unexpected). Documented behavior; acceptable.
- **Apple TV offline.** Pulses still fire, no payload arrives, the existing stale binary sensor flips on after 3× interval. No new failure mode.
- **Reload spam.** Each reload fires one immediate pulse. Pulses are cheap; HomeKit suppresses redundant "turn on" if already on.
- **Unload.** Time-interval unsub fires (via `entry.async_on_unload`), webhook unregisters, in-flight pulse-off task cancelled, switch entity removed.

## Testing

New `tests/test_switch.py`:

- Switch entity created on setup.
- `coordinator.pulse()` flips switch on, then off after `PULSE_DURATION_SECONDS` (advance HA time via `async_fire_time_changed`).
- Rapid pulse calls cancel previous off-unsub before scheduling a new one.
- Manual `async_turn_on` / `async_turn_off` writes state without triggering pulse cycle.

Updated `tests/test_init.py`:

- Time-interval listener registered with correct period.
- Immediate pulse fires on setup.
- Options-flow interval change re-registers listener with new period.
- Unload cancels listener and pulse task.

Existing webhook tests unchanged.

## YAGNI rejections

- Per-HomePod switches.
- "Refresh now" button entity.
- Configurable pulse duration.
- Multi-instance support (config_flow already enforces single-instance).
- Persisted switch state across HA restarts.

## Migration impact

Breaking change for v1.x users. Webhook URL and integration config carry over; only the iOS automation trigger needs to be rebuilt. Documented in the new "Upgrading from 1.x" README section.
