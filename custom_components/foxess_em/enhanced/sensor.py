"""Read-only Home Assistant entities for enhanced shadow diagnostics."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity

_FIELDS = (
    ("enhanced_target_kwh", "Enhanced Target", "kWh"),
    ("charge_required_kwh", "Charge Required", "kWh"),
    ("reserve_kwh", "Reserve", "kWh"),
    ("status", "Status", None),
    ("legacy_delta_kwh", "Legacy Delta", "kWh"),
)


class EnhancedDiagnosticSensor(SensorEntity):
    """A stable, read-only view of one controller field."""

    _attr_should_poll = False

    def __init__(self, controller, entry_id, key, name, unit):
        self._controller = controller
        self._key = key
        self._attr_name = f"FoxESS Enhanced {name}"
        self._attr_unique_id = f"{entry_id}_enhanced_{key}"
        self._attr_native_unit_of_measurement = unit
        self._unsubscribe = None

    @property
    def native_value(self):
        return None if not self.available else getattr(self._controller, self._key)

    @property
    def available(self):
        return bool(
            self._controller.enabled
            and self._controller.status not in {"disabled", "unavailable"}
        )

    @property
    def extra_state_attributes(self):
        return {
            "status": self._controller.status,
            "diagnostics": list(self._controller.diagnostics),
        }

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        self._unsubscribe = self._controller.add_update_listener(self.update_callback)

    async def async_will_remove_from_hass(self):
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None
        await super().async_will_remove_from_hass()

    def update_callback(self):
        self.async_write_ha_state()


def sensors(controller, entry):
    """Build the five diagnostic entities for a config entry."""
    return [
        EnhancedDiagnosticSensor(controller, entry.entry_id, *field)
        for field in _FIELDS
    ]
