"""SCSTC Bus Status integration - minimal init"""
from __future__ import annotations

from datetime import timedelta, datetime
import re
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
            _LOGGER.debug("Fetching cancelations from %s", CANCELATIONS_URL)
            resp = await session.get(CANCELATIONS_URL, timeout=10)
            resp.raise_for_status()
            data = await resp.json()
            _LOGGER.debug("Fetched cancelations (status=%s): %s", resp.status, data)
            return data
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Error fetching cancelations: %s", err)
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

            _LOGGER.debug("Posting bus notifications to %s; bus_numbers=%s; payload=%s", BUS_NOTIFICATIONS_URL, bus_numbers, payload)
            resp = await session.post(BUS_NOTIFICATIONS_URL, json=payload, timeout=10)
            resp.raise_for_status()
            data = await resp.json()
            _LOGGER.debug("Bus POST response (status=%s): %s", resp.status, data)
            return data
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Error fetching bus notifications: %s", err)
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
        # Create a per-entry Bus coordinator that only requests this entry's bus number
        bus_number = entry.data.get("bus_number")
        _LOGGER.debug("Creating Bus coordinator for entry %s bus %s", entry.entry_id, bus_number)

        async def async_update_bus_data_for_entry() -> list:
            """Fetch bus notifications for a single bus number via HTTP POST."""
            try:
                if not bus_number:
                    return []
                search_value = str(bus_number)
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
                _LOGGER.debug("Posting bus notifications for entry %s to %s; payload=%s", entry.entry_id, BUS_NOTIFICATIONS_URL, payload)
                resp = await session.post(BUS_NOTIFICATIONS_URL, json=payload, timeout=10)
                resp.raise_for_status()
                raw = await resp.json()
                _LOGGER.debug("Bus POST response for %s (status=%s): %s", entry.entry_id, resp.status, raw)

                # Extract rows from response
                def _rows_from(raw_data):
                    if not raw_data:
                        return []
                    if isinstance(raw_data, dict):
                        if "d" in raw_data and isinstance(raw_data["d"], dict):
                            inner = raw_data["d"]
                            if isinstance(inner.get("data"), list):
                                return inner.get("data")
                            if isinstance(inner, list):
                                return inner
                        if isinstance(raw_data.get("data"), list):
                            return raw_data.get("data")
                    if isinstance(raw_data, list):
                        return raw_data
                    return []

                rows = _rows_from(raw)
                allowed_keys = {"Action", "AffectsSchools", "Comment", "CreateTimeDisplay", "Operator", "TransferSchools", "RouteRun"}
                results: list[dict] = []
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    # Only include rows where RouteRun matches this bus number
                    route_run = row.get("RouteRun")
                    if route_run is None:
                        continue
                    try:
                        if str(route_run).strip().lower() != str(bus_number).strip().lower():
                            continue
                    except Exception:
                        continue

                    filtered: dict = {}
                    for k in allowed_keys:
                        if k in row:
                            filtered[k] = row.get(k)

                    # Normalize CreateTimeDisplay
                    cts = filtered.get("CreateTimeDisplay")
                    if isinstance(cts, str) and cts:
                        parsed = None
                        try:
                            parsed = datetime.fromisoformat(cts)
                        except Exception:
                            for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%m/%d/%Y %I:%M %p", "%Y-%m-%dT%H:%M:%S%z"):
                                try:
                                    parsed = datetime.strptime(cts, fmt)
                                    break
                                except Exception:
                                    continue
                        if parsed:
                            filtered["CreateTimeDisplay"] = parsed

                    # Extract delay
                    action_text = filtered.get("Action")
                    delay_val = None
                    if isinstance(action_text, str) and action_text:
                        m = re.search(r"Delayed\s+(\d+)\s+minutes", action_text, re.IGNORECASE)
                        if m:
                            try:
                                delay_val = int(m.group(1))
                            except Exception:
                                delay_val = None
                    filtered["Delay"] = delay_val

                    results.append(filtered)

                return results
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.debug("Error fetching bus notifications for %s: %s", entry.entry_id, err)
                raise UpdateFailed(err)

        # create coordinator for this entry
        bus_coordinator = DataUpdateCoordinator(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_bus_{entry.entry_id}",
            update_method=async_update_bus_data_for_entry,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        await bus_coordinator.async_config_entry_first_refresh()

        coordinator = bus_coordinator
        hass.data[DOMAIN]["bus_entries"].add(entry.entry_id)

    # Ensure per-entry storage exists and include an empty sample for Bus entries
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator}
    if entry.data.get("type") == "Bus":
        ent_info = hass.data[DOMAIN].get(entry.entry_id, {})
        if "last_data" not in ent_info:
            empty = {
                # Per-request defaults when no data available for this bus
                "Action": "On time",
                "AffectsSchools": "",
                "Comment": "",
                "CreateTimeDisplay": None,
                "Operator": "",
                "TransferSchools": "",
                "RouteRun": str(entry.data.get("bus_number")) if entry.data.get("bus_number") is not None else None,
                "Delay": 0,
            }
            ent_info["last_data"] = [empty]
            hass.data[DOMAIN][entry.entry_id] = ent_info
        # Ensure coordinator updates propagate to per-entry last_data
        def _on_entry_coordinator_update() -> None:
            latest = coordinator.data or []
            if latest:
                ent_info["last_data"] = latest
            else:
                # Preserve existing keys if present, only update the requested keys
                base = (ent_info.get("last_data") or [{}])[0].copy()
                base["Action"] = "On time"
                base["Comment"] = ""
                base["CreateTimeDisplay"] = None
                base["Delay"] = 0
                ent_info["last_data"] = [base]

        try:
            coordinator.async_add_listener(_on_entry_coordinator_update)
        except Exception:
            # If coordinator doesn't support async_add_listener, ignore
            pass

    # Forward setup for all platforms at once (newer HA API)
    # Await platform setup so the config entry setup does not finish
    # before platforms are ready. This prevents the setup lock from
    # being released prematurely.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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
                # No shared coordinator to remove; per-entry coordinators will be garbage-collected.
                pass

        # If no remaining tracked data, remove the domain key
        if not any(k for k in hass.data.get(DOMAIN, {}) if k):
            hass.data.pop(DOMAIN, None)

        return True
    return False
