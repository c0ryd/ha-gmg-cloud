"""The GMG Cloud integration."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    SCAN_INTERVAL,
    SCAN_INTERVAL_ACTIVE,
    SCAN_INTERVAL_IDLE,
    SCAN_INTERVAL_BURST,
    SCAN_BURST_DURATION,
)
from .api import GMGCloudApi, GMGApiError, GMGAuthError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SELECT]

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_EMAIL): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the GMG Cloud component from YAML."""
    if DOMAIN not in config:
        return True

    conf = config[DOMAIN]
    
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_IMPORT},
            data={
                CONF_EMAIL: conf[CONF_EMAIL],
                CONF_PASSWORD: conf[CONF_PASSWORD],
            },
        )
    )
    
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GMG Cloud from a config entry."""
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]

    api = GMGCloudApi(email, password)

    try:
        await api.async_authenticate()
    except GMGAuthError as err:
        _LOGGER.error("Failed to authenticate with GMG: %s", err)
        return False

    # Get initial list of grills
    grills = await api.async_get_grills()
    if not grills:
        _LOGGER.error("No grills found for account %s", email)
        return False

    _LOGGER.info("Found %d grill(s) for account %s", len(grills), email)
    for grill in grills:
        _LOGGER.info(
            "  - %s (ID: %s, Type: %s)",
            grill.get("grillName"),
            grill.get("grillId"),
            grill.get("connectionType"),
        )

    # Burst mode state: timestamp until which burst polling is active
    burst_state = {"until": 0.0}

    def trigger_burst() -> None:
        """Activate burst polling (1s) for the next SCAN_BURST_DURATION seconds.

        Called by entities after sending a command so the dashboard
        reflects changes almost instantly.
        """
        burst_state["until"] = time.monotonic() + SCAN_BURST_DURATION
        coordinator.update_interval = timedelta(seconds=SCAN_INTERVAL_BURST)
        _LOGGER.debug(
            "Burst polling activated for %ds at %ds interval",
            SCAN_BURST_DURATION,
            SCAN_INTERVAL_BURST,
        )

    async def async_update_data() -> dict:
        """Fetch data from API.

        Uses the correct endpoint: /grill/{connectionType}|{grillId}/state
        discovered from app decompilation.

        Dynamically adjusts polling interval:
        - 1s  burst mode for 30s after a command is sent
        - 2s  when any grill is actively cooking (grillState > 0)
        - 60s when all grills are off
        """
        try:
            data = {"grills": {}}
            any_active = False
            for grill in api.get_cached_grills():
                grill_id = grill.get("grillId")
                if grill_id:
                    state = await api.async_get_grill_state(grill)
                    data["grills"][grill_id] = {
                        "info": grill,
                        "state": state,
                        "online": state is not None,
                    }
                    if state and state.get("grillState", 0) > 0:
                        any_active = True

            # Determine the right polling interval
            now = time.monotonic()
            if now < burst_state["until"]:
                # Burst mode still active -- keep 1s polling
                new_interval = SCAN_INTERVAL_BURST
                mode_label = "burst"
            elif any_active:
                new_interval = SCAN_INTERVAL_ACTIVE
                mode_label = "active"
            else:
                new_interval = SCAN_INTERVAL_IDLE
                mode_label = "idle"

            if coordinator.update_interval != timedelta(seconds=new_interval):
                _LOGGER.debug(
                    "Adjusting polling interval to %ds (%s)",
                    new_interval,
                    mode_label,
                )
                coordinator.update_interval = timedelta(seconds=new_interval)

            return data
        except GMGApiError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=SCAN_INTERVAL),
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinator": coordinator,
        "grills": grills,
        "trigger_burst": trigger_burst,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["api"].async_close()

    return unload_ok
