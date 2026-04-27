# HomePod Sensors — iOS Shortcut Template

This directory contains the iOS Shortcuts automation that bridges HomePod Mini sensor data to Home Assistant.

## Import the Shortcut

> **Download:** [HomePod Sensors Shortcut (iCloud)](https://www.icloud.com/shortcuts/) *(link added on first release)*

Alternatively, build it manually using the steps below.

---

## What the Shortcut Does

Whenever the `switch.homepod_sensors_refresh` entity turns on (driven by the integration's interval timer), the shortcut:

1. Queries HomeKit for all HomePod Mini accessories
2. Reads each device's **temperature** and **humidity** values
3. POSTs a JSON payload to your Home Assistant webhook URL

---

## Shortcut Actions (step-by-step)

Build a new Shortcut in the iOS Shortcuts app with the following actions:

### Action 1 — Get HomeKit accessories
```
Get HomeKit Accessories
  Filter: Type = Thermostat (HomePod Mini reports as Thermostat)
  Store result in: homepods
```

### Action 2 — Build devices list
```
Set Variable: devices = []

Repeat with each item in homepods:
  Get Details of HomeKit Accessory (item)
    → Current Temperature → store as: temp_c
    → Current Relative Humidity → store as: humidity_pct
    → Accessory Serial Number → store as: serial
    → Accessory Name → store as: device_name

  Add to Variable: devices
    {
      "name": device_name,
      "serial": serial,
      "temperature_c": temp_c,
      "humidity_pct": humidity_pct
    }
End Repeat
```

### Action 3 — POST to Home Assistant
```
Get Contents of URL:
  URL: http://<YOUR_HA_IP>:8123/api/webhook/<YOUR_WEBHOOK_TOKEN>
  Method: POST
  Headers:
    Content-Type: application/json
  Body (JSON):
    {
      "devices": devices
    }
```

---

## Automation Setup

Use a **Personal Automation in the Shortcuts app** (not Home → Automation, which uses a restricted action set that doesn't expose *Run Shortcut*).

Prerequisite: `switch.homepod_sensors_refresh` is already exposed to Apple Home via HomeKit Bridge (see the main README, Step 2).

1. Open the **Shortcuts** app → **Automation** tab → **+** → **New Automation**.
2. Search for or scroll to **Accessory** → tap **An Accessory Turns On**.
3. Pick **HomePod Sensors Refresh** → **Next**.
4. Choose **Run Immediately** (so it doesn't ask for confirmation each cycle).
5. Action: **Run Shortcut** → select your **HomePod Sensors** shortcut.
6. Tap **Done**.

The integration flips the switch *off* automatically a couple of seconds after each pulse, so the next interval gets a fresh rising edge.

> **Execution scope:** Personal Automations run on the iPhone. If you need execution to continue while your phone is away, see the main README's discussion of the Home-app vs. Shortcuts-app trigger trade-off.

---

## Expected Payload

```json
{
  "devices": [
    {
      "name": "Living Room HomePod",
      "serial": "H1AB2CD3EF4G",
      "temperature_c": 21.5,
      "humidity_pct": 48.2
    },
    {
      "name": "Bedroom HomePod",
      "serial": "H5XY6ZA7BC8D",
      "temperature_c": 20.1,
      "humidity_pct": 52.0
    }
  ]
}
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| No entities appear | Run the Shortcut manually once; check HA logs |
| Temperature shows wrong | Verify HomeKit accessory type is "Thermostat" |
| Multiple devices show as one | Ensure each HomePod has a unique serial in HomeKit |
| Stale sensor turns ON | iPhone away or Personal Automation paused; check iOS battery optimization and that the switch is still pulsing in HA |

---

## Notes

- The `.shortcut` binary file will be attached to the GitHub release page on first publish
- HomePod Mini must be in the same Apple Home as the iOS device running the Shortcut
- iOS 16.4+ recommended; Shortcuts 5.0+
