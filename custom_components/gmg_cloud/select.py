"""Select platform for GMG Cloud integration -- grill mode selector."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import DOMAIN
from .api import GMGCloudApi

_LOGGER = logging.getLogger(__name__)

# Grill modes and their power-on commands
GRILL_MODES = {
    "grill": "UK001!",   # Standard grill mode
    "smoke": "UK002!",   # Cold smoke mode
    "pizza": "UK003!",   # Pizza mode
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up GMG select entities."""
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    api = data["api"]
    grills = data["grills"]
    trigger_burst = data.get("trigger_burst")

    entities = []
    for grill in grills:
        entities.append(GMGGrillModeSelect(coordinator, api, grill, trigger_burst))

    async_add_entities(entities)


class GMGGrillModeSelect(CoordinatorEntity, SelectEntity):
    """Select entity for choosing grill power-on mode.

    When the grill is powered on, this determines which mode it starts in:
    - grill: Standard grilling (UK001!)
    - smoke: Cold smoke mode (UK002!)
    - pizza: Pizza mode (UK003!)

    Changing the selection while the grill is running will power off
    and restart in the new mode.
    """

    _attr_has_entity_name = True
    _attr_options = list(GRILL_MODES.keys())

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        api: GMGCloudApi,
        grill: dict,
        trigger_burst: callable = None,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._api = api
        self._grill = grill
        self._trigger_burst = trigger_burst
        self._grill_id = grill.get("grillId", "unknown")
        self._grill_name = grill.get("grillName", "GMG Grill")

        self._attr_unique_id = f"gmg_cloud_{self._grill_id}_grill_mode"
        self._attr_name = "Grill Mode"
        self._attr_current_option = "grill"  # Default

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
        """Return icon based on current mode."""
        mode = self._attr_current_option
        if mode == "smoke":
            return "mdi:smoke"
        elif mode == "pizza":
            return "mdi:pizza"
        return "mdi:grill"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator.

        Map grillState to the mode selector:
        grillState 1 = grillMode, 3 = smokeMode.
        grillMode field may also indicate pizza mode.
        """
        if self.coordinator.data:
            grill_data = self.coordinator.data.get("grills", {}).get(self._grill_id)
            if grill_data:
                state = grill_data.get("state")
                if state:
                    grill_state = state.get("grillState", 0)
                    grill_mode = state.get("grillMode", 0)
                    if grill_state == 3:
                        self._attr_current_option = "smoke"
                    elif grill_mode == 3:
                        self._attr_current_option = "pizza"
                    elif grill_state in (1, 2):
                        self._attr_current_option = "grill"
                    # When off (grillState==0), keep the last selected mode
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the grill mode.

        If the grill is currently running, this will restart it in the new mode.
        If the grill is off, this just sets the mode for the next power-on.
        """
        self._attr_current_option = option

        # Check if grill is currently on
        is_on = False
        if self.coordinator.data:
            grill_data = self.coordinator.data.get("grills", {}).get(self._grill_id)
            if grill_data and grill_data.get("state"):
                grill_state = grill_data["state"].get("grillState", 0)
                is_on = grill_state in (1, 3)  # grillMode or smokeMode

        if is_on:
            # Grill is running -- power off then restart in new mode
            await self._api.async_power_off(self._grill)
            # Send power-on in the new mode
            if option == "smoke":
                await self._api.async_power_on_smoke(self._grill)
            elif option == "pizza":
                await self._api.async_power_on_pizza(self._grill)
            else:
                await self._api.async_power_on_grill(self._grill)

        self.async_write_ha_state()
        if self._trigger_burst:
            self._trigger_burst()
        await self.coordinator.async_request_refresh()
