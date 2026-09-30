"""Sensor platform for foxess_em."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .average import average_sensor
from .battery import battery_sensor
from .const import DOMAIN
from .forecast import forecast_sensor
from .enhanced import sensor as enhanced_sensor

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_devices
) -> None:
    """Setup sensor platform."""

    controllers = hass.data[DOMAIN][entry.entry_id]["controllers"]

    history_sensors = average_sensor.sensors(controllers, entry)
    solcast_sensors = forecast_sensor.sensors(controllers, entry)
    battery_sensors = battery_sensor.sensors(controllers, entry)

    enhanced = hass.data[DOMAIN][entry.entry_id].get("enhanced")
    enhanced_sensors = [] if enhanced is None else enhanced_sensor.sensors(enhanced, entry)
    entities = solcast_sensors + history_sensors + battery_sensors + enhanced_sensors

    async_add_devices(entities)
