"""Constants for HomePod Sensors integration."""
from __future__ import annotations

DOMAIN = "homepod_sensors"
NAME = "HomePod Sensors"

CONF_UPDATE_INTERVAL = "update_interval"
CONF_WEBHOOK_ID = "webhook_id"

DEFAULT_UPDATE_INTERVAL = 5  # minutes
DEFAULT_STALENESS_MULTIPLIER = 3  # stale after 3x the update interval
PULSE_DURATION_SECONDS = 2  # how long the refresh switch stays "on" per pulse

PLATFORMS = ["sensor", "binary_sensor"]
