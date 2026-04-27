# HomePod Sensors — iOS Shortcut Template

This directory contains the iOS Shortcuts automation that bridges HomePod Mini sensor data to Home Assistant.

## Import the Shortcut

> **Download:** [HomePod Sensors Shortcut (iCloud)](https://www.icloud.com/shortcuts/) *(link added on first release)*

Alternatively, build it manually using the steps below.

---

## What the Shortcut Does

Every **5 minutes** (default), the shortcut:

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

The integration's switch entity is the trigger. Once it is exposed via HomeKit Bridge, set up an automation in the iPhone **Home** app:

1. Open **Home → Automation → +**.
2. Trigger: **An Accessory Is Controlled** → **HomePod Sensors Refresh** → **Turns On**.
3. Action: **Run Shortcut** → select *HomePod Sensors*.
4. Confirm the Home Hub badge ("Run At Home Hub") appears, then save.

The integration sets the switch *off* automatically a couple of seconds after each pulse, so the next interval gets a fresh "turns on" edge.

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
| Stale sensor turns ON | Shortcut automation may have stopped; check iOS battery optimization |

---

## Notes

- The `.shortcut` binary file will be attached to the GitHub release page on first publish
- HomePod Mini must be in the same Apple Home as the iOS device running the Shortcut
- iOS 16.4+ recommended; Shortcuts 5.0+
