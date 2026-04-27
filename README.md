# HomePod Sensors for Home Assistant

[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io)

Expose your **HomePod Mini temperature and humidity sensors** in Home Assistant.

Apple enables the HomePod Mini's built-in sensors in the Apple Home app but deliberately blocks third-party access via the HomeKit Controller API. This integration bridges the gap: it exposes a switch entity that pulses on a configurable interval, and an iOS Shortcuts Personal Automation running on your iPhone POSTs the latest temperature and humidity to a Home Assistant webhook each time the switch turns on.

---

## Features

- 🌡️ **Temperature sensor** per HomePod Mini
- 💧 **Humidity sensor** per HomePod Mini
- ⚠️ **Stale data sensor** — alerts when iOS has stopped pushing updates
- 🔍 **Auto-discovery** — new HomePods appear automatically when they first report in
- ⚙️ **Configurable interval** — set how often the Shortcut runs (1–60 min)
- 📦 **Zero dependencies** — no extra Python packages required
- 🏠 **Local push** — data never leaves your home network

---

## Requirements

- Home Assistant 2024.1 or newer
- [HACS](https://hacs.xyz) installed
- An iPhone or iPad on the same Apple Home as your HomePod Mini(s)
- iOS 16.2 or newer (for HomePod sensor access in Shortcuts)

---

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → **⋮** → **Custom repositories**
2. Add `https://github.com/pujux/ha-homepod-sensors` as an **Integration**
3. Search for **HomePod Sensors** and install
4. Restart Home Assistant

### Manual

Copy `custom_components/homepod_sensors/` to your HA `config/custom_components/` directory and restart.

---

## Setup

### Step 1 — Add the Integration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **HomePod Sensors**
3. Note the **webhook URL** displayed (you'll need it in Step 2)
4. Set your preferred update interval (default: 5 minutes)
5. Click **Submit**

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

### Step 4 — Create the Personal Automation

Use the **Shortcuts** app (not the Home app — Home → Automation uses a restricted action set that does *not* expose *Run Shortcut*).

1. Open **Shortcuts → Automation → + → New Automation**.
2. Search/scroll to **Accessory** → tap **An Accessory Turns On**.
3. Pick **HomePod Sensors Refresh** → **Next**.
4. Choose **Run Immediately** so each pulse fires the Shortcut without confirmation.
5. Action: **Run Shortcut** → select your *HomePod Sensors* shortcut.
6. Tap **Done**.

> **Execution scope:** Personal Automations run on the iPhone — they fire when the iPhone is on the same network as the HomePods. If you need automation execution to continue while your iPhone is away, the trade-off is that Home-app automations *can* run on Apple TV / HomePod / iPad Home Hubs but their action set excludes *Run Shortcut*, so the data-collection actions would have to be inlined. See the [shortcuts/README.md](shortcuts/README.md) for that variant.

### Transport security

The webhook URL contains a long-lived token in its path. **Do not POST over plain HTTP on a network you don't fully trust** — anyone on the same Wi-Fi can sniff the token and the sensor data, and (with the token) can spoof readings.

Recommended local-HTTPS options:

- A reverse proxy (Caddy, NGINX, Traefik) terminating TLS with a Let's Encrypt certificate via DNS-01 challenge.
- Tailscale or WireGuard between the iOS device and HA.
- HA core HTTPS configured with `ssl_certificate` / `ssl_key`.

Nabu Casa's remote URL also works but routes traffic over the internet — overkill for an integration whose entire premise is a local push.

### Step 5 — Verify

Run the Shortcut once manually (tap the switch in the Home app, or tap ▷ on the Shortcut). Within a few seconds, devices should appear under **Settings → Devices & Services → HomePod Sensors**.

---

## Entities

Each HomePod Mini device gets:

| Entity | Type | Description |
|--------|------|-------------|
| `sensor.<name>_temperature` | Sensor | Room temperature (°C) |
| `sensor.<name>_humidity` | Sensor | Relative humidity (%) |
| `sensor.<name>_last_updated` | Sensor | Last push time (diagnostic, hidden by default) |
| `binary_sensor.<name>_stale` | Binary sensor | ON if no update received in >3× the interval |

---

## Example Automations

**Alert when data stops arriving:**
```yaml
automation:
  - alias: "HomePod sensor stale alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.living_room_homepod_stale
        to: "on"
        for: "00:05:00"
    action:
      - service: notify.mobile_app
        data:
          message: "HomePod sensor data is stale — check your iOS Shortcut"
```

**Climate control based on HomePod temperature:**
```yaml
automation:
  - alias: "Cool down living room"
    trigger:
      - platform: numeric_state
        entity_id: sensor.living_room_homepod_temperature
        above: 25
    action:
      - service: climate.set_temperature
        target:
          entity_id: climate.living_room_ac
        data:
          temperature: 22
```

---

## Troubleshooting

**No devices appearing after running the Shortcut**
- Check that your HA webhook URL is reachable from your iPhone (try opening it in Safari)
- Ensure the JSON body in your Shortcut includes `serial`, `name`, `temperature_c`, and `humidity_pct`
- Check HA logs: **Settings → System → Logs** → search for `homepod_sensors`

**Sensors show as unavailable**
- The integration has not received data yet — run the Shortcut manually once to populate initial values

**Stale sensor is always ON**
- Your iOS Shortcut may not be running. Check **Shortcuts → Automation** and ensure it is enabled and not paused by iOS Low Power Mode

---

## Upgrading from 1.x

Version 2.0 changes the Shortcut trigger from "Time of Day" to "Accessory Turns On". Your webhook URL and existing HA configuration carry over — only the iOS automation needs to be rebuilt:

1. Update the integration via HACS and restart Home Assistant.
2. Open the **Home** app and add `switch.homepod_sensors_refresh` to your HomeKit Bridge include list (see Step 2 above).
3. Delete your old "Time of Day" automation in the **Shortcuts** app.
4. Create the new accessory-triggered Personal Automation in the **Shortcuts** app (see Step 4 above).

## Version History

| Version | Changes |
|---------|---------|
| 2.0.0 | Replaces time-of-day Shortcut trigger with an integration-owned switch entity that pulses on the configured interval. Trigger is now a Shortcuts-app Personal Automation listening for the switch turning on. **Breaking:** existing users must rebuild their iOS automation — see *Upgrading from 1.x*. |
| 1.0.0 | Initial release — webhook bridge, auto-discovery, temp/humidity/stale entities |

---

## License

MIT
