"""SCSTC Bus Status integration - minimal init"""
from __future__ import annotations

from datetime import timedelta
import asyncio
import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CANCELATIONS_URL, UPDATE_INTERVAL, BUS_NOTIFICATIONS_URL

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the integration from configuration.yaml (if any)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up the integration from a config entry (UI).

    Create a DataUpdateCoordinator to fetch the cancellation JSON and
    store it on hass.data for platforms to use.
    """
    hass.data.setdefault(DOMAIN, {})

    session = async_get_clientsession(hass)

    entry_type = entry.data.get("type", "Cancelation")

    async def async_update_cancelation_data():
        try:
            # Single source for both types for now; can be customized per type.
            resp = await session.get(CANCELATIONS_URL, timeout=10)
            resp.raise_for_status()
            data = await resp.json()
            return data
        except Exception as err:  # pylint: disable=broad-except
            raise UpdateFailed(err)

    async def async_update_bus_data():
        """Fetch bus notifications via HTTP POST (mirrors bus.py).

        This posts a JSON payload to the bus notifications endpoint and
        returns the parsed JSON response.
        """
        try:
            # Gather bus numbers from all Bus config entries for this domain
            entries = hass.config_entries.async_entries(DOMAIN)
            bus_numbers = [str(e.data.get("bus_number")) for e in entries if e.data.get("type") == "Bus" and e.data.get("bus_number")]
            # If there are no bus numbers configured, skip the POST and return empty data
            if not bus_numbers:
                return {}
            # create comma-separated search value
            search_value = ",".join(bus_numbers)

            # Build payload similar to bus.py; set search.value to the comma-separated list
            payload = {
                "alertCondition": {"RangeType": ""},
                "dataTableData": {
                    "draw": 1,
                    "length": 100,
                    "start": 0,
                    "order": [{"column": 2, "dir": "asc"}],
                    "search": {"value": search_value, "regex": False},
                    "SortFieldName": "RouteRun",
                },
            }

            resp = await session.post(BUS_NOTIFICATIONS_URL, json=payload, timeout=10)
            resp.raise_for_status()
            data = await resp.json()
            return data
        except Exception as err:  # pylint: disable=broad-except
            raise UpdateFailed(err)

    # Ensure tracking structures exist
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("cancelation_entries", set())
    hass.data[DOMAIN].setdefault("bus_entries", set())

    coordinator = None

    if entry_type == "Cancelation":
        # Create or reuse the shared Cancelation coordinator
        if "cancelation_coordinator" not in hass.data[DOMAIN]:
            _LOGGER.debug("Creating Cancelation coordinator")
            cancel_coordinator = DataUpdateCoordinator(
                hass,
                _LOGGER,
                name=f"{DOMAIN}_cancelation",
                update_method=async_update_cancelation_data,
                update_interval=timedelta(seconds=UPDATE_INTERVAL),
            )
            # perform initial refresh
            await cancel_coordinator.async_config_entry_first_refresh()
            hass.data[DOMAIN]["cancelation_coordinator"] = cancel_coordinator
        coordinator = hass.data[DOMAIN]["cancelation_coordinator"]
        hass.data[DOMAIN]["cancelation_entries"].add(entry.entry_id)

    else:
        # Bus entries share a single coordinator
        if "bus_coordinator" not in hass.data[DOMAIN]:
            _LOGGER.debug("Creating Bus coordinator")
            bus_coordinator = DataUpdateCoordinator(
                hass,
                _LOGGER,
                name=f"{DOMAIN}_bus",
                update_method=async_update_bus_data,
                update_interval=timedelta(seconds=UPDATE_INTERVAL),
            )
            await bus_coordinator.async_config_entry_first_refresh()
            hass.data[DOMAIN]["bus_coordinator"] = bus_coordinator
        coordinator = hass.data[DOMAIN]["bus_coordinator"]
        hass.data[DOMAIN]["bus_entries"].add(entry.entry_id)

    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}

    # Forward setup for all platforms at once (newer HA API)
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry and its platforms."""
    results = await asyncio.gather(
        *[hass.config_entries.async_forward_entry_unload(entry, platform) for platform in PLATFORMS]
    )
    if all(results):
        # Remove entry mapping
        entry_info = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)

        # Remove from type-specific tracking and clean up coordinators when no entries remain
        if entry.data.get("type") == "Cancelation":
            entries = hass.data[DOMAIN].get("cancelation_entries", set())
            entries.discard(entry.entry_id)
            if not entries:
                hass.data[DOMAIN].pop("cancelation_coordinator", None)
        else:
            entries = hass.data[DOMAIN].get("bus_entries", set())
            entries.discard(entry.entry_id)
            if not entries:
                hass.data[DOMAIN].pop("bus_coordinator", None)

        # If no remaining tracked data, remove the domain key
        if not any(k for k in hass.data.get(DOMAIN, {}) if k):
            hass.data.pop(DOMAIN, None)

        return True
    return False
