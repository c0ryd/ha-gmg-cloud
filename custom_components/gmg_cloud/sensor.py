"""Sensor platform for GMG Cloud integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.entity import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Warning codes from app decompilation (warningItemBuilder)
WARNING_CODES = {
    0: "none",
    1: "fan_mode",
    2: "low_pellets",
    3: "ignitor_disconnect",
    4: "auger_disconnect",
    5: "fan_disconnect",
}

# grillState enum from app decompilation
GRILL_STATES = {
    0: "off",
    1: "grilling",
    2: "fan_mode",
    3: "smoking",
}


def _device_info(grill: dict, grill_id: str, grill_name: str) -> dict[str, Any]:
    """Return shared device info for all sensors."""
    return {
        "identifiers": {(DOMAIN, grill_id)},
        "name": grill_name,
        "manufacturer": "Green Mountain Grills",
        "model": grill.get("bleName", "GMG Grill"),
    }


def _get_state(coordinator: DataUpdateCoordinator, grill_id: str) -> dict | None:
    """Get the grill state dict from coordinator data."""
    if coordinator.data:
        grill_data = coordinator.data.get("grills", {}).get(grill_id)
        if grill_data:
            return grill_data.get("state")
    return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GMG sensor entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    grills = data["grills"]

    entities = []
    for grill in grills:
        grill_id = grill.get("grillId", "unknown")

        # Temperature sensors
        entities.append(GMGProbeSensor(coordinator, grill, "probe1", "Food Probe 1", "foodTemp"))
        entities.append(GMGProbeSensor(coordinator, grill, "probe2", "Food Probe 2", "foodTemp2"))
        entities.append(GMGProbeSensor(coordinator, grill, "target_grill", "Target Grill Temp", "setGrillTemp"))
        entities.append(GMGProbeSensor(coordinator, grill, "target_probe1", "Target Probe 1 Temp", "setFoodTemp"))
        entities.append(GMGProbeSensor(coordinator, grill, "target_probe2", "Target Probe 2 Temp", "setFoodTemp2"))

        # Status sensors
        entities.append(GMGStatusSensor(coordinator, grill))
        entities.append(GMGWarningSensor(coordinator, grill))
        entities.append(GMGFireStateSensor(coordinator, grill))
        entities.append(GMGProfileSensor(coordinator, grill))
        entities.append(GMGFirmwareSensor(coordinator, grill))
        entities.append(GMGLastUpdatedSensor(coordinator, grill))

    async_add_entities(entities)


class GMGProbeSensor(CoordinatorEntity, SensorEntity):
    """GMG temperature sensor -- used for grill temp, probe temps, and target temps."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        grill: dict,
        key: str,
        name: str,
        api_field: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._grill = grill
        self._grill_id = grill.get("grillId", "unknown")
        self._grill_name = grill.get("grillName", "GMG Grill")
        self._api_field = api_field

        self._attr_unique_id = f"gmg_cloud_{self._grill_id}_{key}"
        self._attr_name = name
        self._attr_native_value = None

    @property
    def available(self) -> bool:
        return True

    @property
    def device_info(self) -> dict[str, Any]:
        return _device_info(self._grill, self._grill_id, self._grill_name)

    @callback
    def _handle_coordinator_update(self) -> None:
        state = _get_state(self.coordinator, self._grill_id)
        if state:
            val = state.get(self._api_field)
            # Target temps of 0 mean "not set" -- show as None
            if self._api_field.startswith("set") and val == 0:
                self._attr_native_value = None
            else:
                self._attr_native_value = val
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class GMGStatusSensor(CoordinatorEntity, SensorEntity):
    """GMG grill connection/operating status sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DataUpdateCoordinator, grill: dict) -> None:
        super().__init__(coordinator)
        self._grill = grill
        self._grill_id = grill.get("grillId", "unknown")
        self._grill_name = grill.get("grillName", "GMG Grill")
        self._attr_unique_id = f"gmg_cloud_{self._grill_id}_status"
        self._attr_name = "Status"
        self._attr_native_value = "offline"

    @property
    def available(self) -> bool:
        return True

    @property
    def device_info(self) -> dict[str, Any]:
        return _device_info(self._grill, self._grill_id, self._grill_name)

    @property
    def icon(self) -> str:
        val = self._attr_native_value
        if val in ("grilling", "smoking"):
            return "mdi:fire"
        elif val == "fan_mode":
            return "mdi:fan"
        elif val == "online":
            return "mdi:grill"
        return "mdi:grill-outline"

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data:
            grill_data = self.coordinator.data.get("grills", {}).get(self._grill_id)
            if grill_data and grill_data.get("online"):
                state = grill_data.get("state", {})
                grill_state = state.get("grillState", 0)
                self._attr_native_value = GRILL_STATES.get(grill_state, "active")
            else:
                self._attr_native_value = "offline"
        self.async_write_ha_state()


class GMGWarningSensor(CoordinatorEntity, SensorEntity):
    """GMG active warning sensor.

    Warning codes from app decompilation:
    0=none, 1=fan_mode, 2=low_pellets, 3=ignitor_disconnect,
    4=auger_disconnect, 5=fan_disconnect.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: DataUpdateCoordinator, grill: dict) -> None:
        super().__init__(coordinator)
        self._grill = grill
        self._grill_id = grill.get("grillId", "unknown")
        self._grill_name = grill.get("grillName", "GMG Grill")
        self._attr_unique_id = f"gmg_cloud_{self._grill_id}_warning"
        self._attr_name = "Warning"
        self._attr_native_value = "none"

    @property
    def available(self) -> bool:
        return True

    @property
    def device_info(self) -> dict[str, Any]:
        return _device_info(self._grill, self._grill_id, self._grill_name)

    @property
    def icon(self) -> str:
        val = self._attr_native_value
        if val == "none":
            return "mdi:check-circle-outline"
        elif val == "low_pellets":
            return "mdi:fire-alert"
        elif val in ("fan_mode", "fan_disconnect"):
            return "mdi:fan-alert"
        elif val == "ignitor_disconnect":
            return "mdi:fire-off"
        elif val == "auger_disconnect":
            return "mdi:cog-off"
        return "mdi:alert-circle"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = _get_state(self.coordinator, self._grill_id)
        if state:
            return {"warning_code": state.get("warningCode", 0)}
        return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        state = _get_state(self.coordinator, self._grill_id)
        if state:
            code = state.get("warningCode", 0)
            self._attr_native_value = WARNING_CODES.get(code, f"unknown_{code}")
        else:
            self._attr_native_value = "none"
        self.async_write_ha_state()


class GMGFireStateSensor(CoordinatorEntity, SensorEntity):
    """GMG fire/ignitor state sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DataUpdateCoordinator, grill: dict) -> None:
        super().__init__(coordinator)
        self._grill = grill
        self._grill_id = grill.get("grillId", "unknown")
        self._grill_name = grill.get("grillName", "GMG Grill")
        self._attr_unique_id = f"gmg_cloud_{self._grill_id}_fire_state"
        self._attr_name = "Fire State"
        self._attr_native_value = None

    @property
    def available(self) -> bool:
        return True

    @property
    def device_info(self) -> dict[str, Any]:
        return _device_info(self._grill, self._grill_id, self._grill_name)

    @property
    def icon(self) -> str:
        return "mdi:fire" if self._attr_native_value else "mdi:fire-off"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = _get_state(self.coordinator, self._grill_id)
        if state:
            return {"fire_state_progress": state.get("fireStateProgress", 0)}
        return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        state = _get_state(self.coordinator, self._grill_id)
        if state:
            self._attr_native_value = state.get("fireState", 0)
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class GMGProfileSensor(CoordinatorEntity, SensorEntity):
    """GMG cook profile status sensor."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: DataUpdateCoordinator, grill: dict) -> None:
        super().__init__(coordinator)
        self._grill = grill
        self._grill_id = grill.get("grillId", "unknown")
        self._grill_name = grill.get("grillName", "GMG Grill")
        self._attr_unique_id = f"gmg_cloud_{self._grill_id}_profile"
        self._attr_name = "Cook Profile"
        self._attr_native_value = "none"

    @property
    def available(self) -> bool:
        return True

    @property
    def device_info(self) -> dict[str, Any]:
        return _device_info(self._grill, self._grill_id, self._grill_name)

    @property
    def icon(self) -> str:
        if self._attr_native_value != "none":
            return "mdi:playlist-play"
        return "mdi:playlist-remove"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = _get_state(self.coordinator, self._grill_id)
        if state:
            remaining = state.get("profileRemainingTime", 0)
            # 4294967295 (0xFFFFFFFF) means no profile / infinite
            if remaining == 4294967295:
                remaining_display = None
            else:
                remaining_display = remaining
            return {
                "profile_id": state.get("curProfileId", 0),
                "profile_step": state.get("curProfileStepId", 0),
                "num_steps": state.get("numProfileSteps", 0),
                "paused": bool(state.get("curProfilePaused", 0)),
                "remaining_seconds": remaining_display,
                "end_mode": state.get("profileEndMode", 0),
            }
        return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        state = _get_state(self.coordinator, self._grill_id)
        if state:
            profile_id = state.get("curProfileId", 0)
            paused = state.get("curProfilePaused", 0)
            if profile_id > 0:
                if paused:
                    self._attr_native_value = "paused"
                else:
                    self._attr_native_value = "active"
            else:
                self._attr_native_value = "none"
        else:
            self._attr_native_value = "none"
        self.async_write_ha_state()


class GMGFirmwareSensor(CoordinatorEntity, SensorEntity):
    """GMG firmware version sensor."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DataUpdateCoordinator, grill: dict) -> None:
        super().__init__(coordinator)
        self._grill = grill
        self._grill_id = grill.get("grillId", "unknown")
        self._grill_name = grill.get("grillName", "GMG Grill")
        self._attr_unique_id = f"gmg_cloud_{self._grill_id}_firmware"
        self._attr_name = "Firmware Version"
        self._attr_native_value = None

    @property
    def available(self) -> bool:
        return True

    @property
    def device_info(self) -> dict[str, Any]:
        return _device_info(self._grill, self._grill_id, self._grill_name)

    @property
    def icon(self) -> str:
        return "mdi:chip"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = _get_state(self.coordinator, self._grill_id)
        if state:
            return {"software_path": state.get("softwarePath")}
        return {}

    @callback
    def _handle_coordinator_update(self) -> None:
        state = _get_state(self.coordinator, self._grill_id)
        if state:
            self._attr_native_value = state.get("firmwareVersion")
        else:
            self._attr_native_value = None
        self.async_write_ha_state()


class GMGLastUpdatedSensor(CoordinatorEntity, SensorEntity):
    """GMG last updated timestamp sensor."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: DataUpdateCoordinator, grill: dict) -> None:
        super().__init__(coordinator)
        self._grill = grill
        self._grill_id = grill.get("grillId", "unknown")
        self._grill_name = grill.get("grillName", "GMG Grill")
        self._attr_unique_id = f"gmg_cloud_{self._grill_id}_last_updated"
        self._attr_name = "Last Updated"
        self._attr_native_value = None

    @property
    def available(self) -> bool:
        return True

    @property
    def device_info(self) -> dict[str, Any]:
        return _device_info(self._grill, self._grill_id, self._grill_name)

    @callback
    def _handle_coordinator_update(self) -> None:
        from datetime import datetime, timezone

        state = _get_state(self.coordinator, self._grill_id)
        if state:
            ts = state.get("lastUpdated")
            if ts:
                try:
                    # Parse ISO timestamp, handle nanoseconds by truncating
                    # e.g. "2026-02-08T06:36:20.744505113Z"
                    if "." in ts:
                        base, frac = ts.split(".")
                        frac = frac.rstrip("Z")[:6]  # Truncate to microseconds
                        ts = f"{base}.{frac}+00:00"
                    else:
                        ts = ts.rstrip("Z") + "+00:00"
                    self._attr_native_value = datetime.fromisoformat(ts)
                except (ValueError, TypeError):
                    self._attr_native_value = None
            else:
                self._attr_native_value = None
        else:
            self._attr_native_value = None
        self.async_write_ha_state()
