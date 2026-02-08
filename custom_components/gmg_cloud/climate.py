"""Climate platform for GMG Cloud integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import (
    DOMAIN,
    MIN_TEMP_F,
    MAX_TEMP_F,
    GRILL_MODE_OFF,
    GRILL_MODE_GRILL,
    GRILL_MODE_SMOKE,
)
from .api import GMGCloudApi

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GMG climate entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    grills = data["grills"]

    entities = []
    for grill in grills:
        entities.append(GMGClimateEntity(coordinator, api, grill))

    async_add_entities(entities)


class GMGClimateEntity(CoordinatorEntity, ClimateEntity):
    """GMG Grill climate entity."""

    _attr_has_entity_name = True
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_min_temp = MIN_TEMP_F
    _attr_max_temp = MAX_TEMP_F
    _attr_target_temperature_step = 5

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: GMGCloudApi,
        grill: dict,
    ) -> None:
        """Initialize the climate entity."""
        super().__init__(coordinator)
        self._api = api
        self._grill = grill
        self._grill_id = grill.get("grillId", "unknown")
        self._grill_name = grill.get("grillName", "GMG Grill")
        
        self._attr_unique_id = f"gmg_cloud_{self._grill_id}"
        self._attr_name = self._grill_name
        
        # State
        self._target_temp: float | None = 225  # Default smoking temp
        self._current_temp: float | None = None
        self._hvac_mode = HVACMode.OFF
        self._is_online = False

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
    def available(self) -> bool:
        """Return if entity is available."""
        # Always available for control, but state may be unknown
        return True

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        return self._hvac_mode

    @property
    def current_temperature(self) -> float | None:
        """Return current temperature."""
        return self._current_temp

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        return self._target_temp

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs = {
            "grill_id": self._grill_id,
            "connection_type": self._grill.get("connectionType"),
            "online": self._is_online,
        }
        # Add live state fields if available
        if self.coordinator.data:
            grill_data = self.coordinator.data.get("grills", {}).get(self._grill_id)
            if grill_data and grill_data.get("state"):
                state = grill_data["state"]
                attrs.update({
                    "fire_state": state.get("fireState"),
                    "grill_state": state.get("grillState"),
                    "grill_mode": state.get("grillMode"),
                    "warning_code": state.get("warningCode"),
                    "firmware_version": state.get("firmwareVersion"),
                    "last_updated": state.get("lastUpdated"),
                })
        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            grill_data = self.coordinator.data.get("grills", {}).get(self._grill_id)
            if grill_data:
                self._is_online = grill_data.get("online", False)
                state = grill_data.get("state")
                if state:
                    # Parse state data -- field names from the API response
                    self._current_temp = state.get("grillTemp")
                    target = state.get("setGrillTemp")
                    if target and target > 0:
                        self._target_temp = target

                    # Determine HVAC mode from grillState enum
                    # grillState: 0=off, 1=grillMode, 2=fanMode, 3=smokeMode
                    grill_state = state.get("grillState", 0)
                    if grill_state > 0:
                        self._hvac_mode = HVACMode.HEAT
                    else:
                        self._hvac_mode = HVACMode.OFF
                else:
                    self._is_online = False

        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode (power on/off).

        Power on defaults to grill mode. Use the grill_mode service
        or extra state attributes to switch between grill/smoke/pizza.
        """
        if hvac_mode == HVACMode.OFF:
            if await self._api.async_power_off(self._grill):
                self._hvac_mode = HVACMode.OFF
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()
        elif hvac_mode == HVACMode.HEAT:
            if await self._api.async_power_on_grill(self._grill):
                self._hvac_mode = HVACMode.HEAT
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set grill target temperature (150-550°F)."""
        if ATTR_TEMPERATURE in kwargs:
            temp = int(kwargs[ATTR_TEMPERATURE])
            if await self._api.async_set_grill_temp(self._grill, temp):
                self._target_temp = temp
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()

    async def async_turn_on(self) -> None:
        """Turn the grill on."""
        await self.async_set_hvac_mode(HVACMode.HEAT)

    async def async_turn_off(self) -> None:
        """Turn the grill off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
