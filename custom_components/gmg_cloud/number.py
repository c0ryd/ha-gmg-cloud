"""Number platform for GMG Cloud integration -- food probe target temperatures."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .api import GMGCloudApi

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GMG number entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    grills = data["grills"]

    entities = []
    for grill in grills:
        entities.append(
            GMGProbeTargetNumber(coordinator, api, grill, probe=1)
        )
        entities.append(
            GMGProbeTargetNumber(coordinator, api, grill, probe=2)
        )

    async_add_entities(entities)


class GMGProbeTargetNumber(CoordinatorEntity, NumberEntity):
    """Number entity for setting food probe target temperature.

    Probe 1: UF{NNN}! command, reads setFoodTemp from state.
    Probe 2: Uf{NNN}! command, reads setFoodTemp2 from state.
    """

    _attr_has_entity_name = True
    _attr_device_class = NumberDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 100
    _attr_native_max_value = 250
    _attr_native_step = 1

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: GMGCloudApi,
        grill: dict,
        probe: int,
    ) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator)
        self._api = api
        self._grill = grill
        self._probe = probe
        self._grill_id = grill.get("grillId", "unknown")
        self._grill_name = grill.get("grillName", "GMG Grill")

        self._attr_unique_id = f"gmg_cloud_{self._grill_id}_probe{probe}_target"
        self._attr_name = f"Probe {probe} Target Temp"
        self._attr_native_value = None
        self._api_field = "setFoodTemp" if probe == 1 else "setFoodTemp2"

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device info."""
        return {
            "identifiers": {(DOMAIN, self._grill_id)},
            "name": self._grill_name,
            "manufacturer": "Green Mountain Grills",
            "model": self._grill.get("bleName", "GMG Grill"),
        }

    @property
    def icon(self) -> str:
        """Return icon."""
        return "mdi:thermometer-lines"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            grill_data = self.coordinator.data.get("grills", {}).get(self._grill_id)
            if grill_data:
                state = grill_data.get("state")
                if state:
                    val = state.get(self._api_field, 0)
                    # 0 means "not set" -- show as None
                    self._attr_native_value = val if val > 0 else None
                else:
                    self._attr_native_value = None
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the probe target temperature."""
        temp = int(value)
        if self._probe == 1:
            success = await self._api.async_set_food_probe1_temp(self._grill, temp)
        else:
            success = await self._api.async_set_food_probe2_temp(self._grill, temp)

        if success:
            self._attr_native_value = temp
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
