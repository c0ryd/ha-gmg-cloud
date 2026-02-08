"""Binary sensor platform for GMG Cloud integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GMG binary sensor entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    grills = data["grills"]

    entities = []
    for grill in grills:
        entities.append(GMGLowPelletsSensor(coordinator, grill))

    async_add_entities(entities)


class GMGLowPelletsSensor(CoordinatorEntity, BinarySensorEntity):
    """GMG low pellets binary sensor.

    Triggers when warningCode == 2 (low_pellets), discovered from
    the app's warningItemBuilder in gmg_warning_view.dart.
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        grill: dict,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._grill = grill
        self._grill_id = grill.get("grillId", "unknown")
        self._grill_name = grill.get("grillName", "GMG Grill")

        self._attr_unique_id = f"gmg_cloud_{self._grill_id}_low_pellets"
        self._attr_name = "Low Pellets"
        self._attr_is_on = False

    @property
    def available(self) -> bool:
        return True

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, self._grill_id)},
            "name": self._grill_name,
            "manufacturer": "Green Mountain Grills",
            "model": self._grill.get("bleName", "GMG Grill"),
        }

    @property
    def icon(self) -> str:
        return "mdi:fire-alert" if self._attr_is_on else "mdi:fire"

    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data:
            grill_data = self.coordinator.data.get("grills", {}).get(self._grill_id)
            if grill_data:
                state = grill_data.get("state")
                if state:
                    # warningCode 2 = low pellets
                    self._attr_is_on = state.get("warningCode", 0) == 2
                else:
                    self._attr_is_on = False
        self.async_write_ha_state()
