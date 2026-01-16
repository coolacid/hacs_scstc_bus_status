"""Minimal sensor platform for SCSTC Bus Status integration.

Creates two sensors per root key in the cancellation JSON:
- <key> status
- <key> note

Each entity reads its value from the DataUpdateCoordinator stored
under `hass.data[DOMAIN][entry.entry_id]["coordinator"]`.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Legacy YAML setup is not supported; sensors are created via UI entries only."""
    return


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up sensors from a config entry.

    This will create `status` and `note` sensors for each top-level key
    in the fetched JSON data.
    """
    # Only create the existing status/note entities for Cancelation entries
    if entry.data.get("type") != "Cancelation":
        return

    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    data = coordinator.data or {}

    entities: list[CoordinatorEntity] = []

    for key in data.keys():
        # sensor for status
        entities.append(MySensorValue(coordinator, entry.entry_id, key, "status", "Cancelation"))
        # sensor for note
        entities.append(MySensorValue(coordinator, entry.entry_id, key, "note", "Cancelation"))

    async_add_entities(entities, True)


class MySensorValue(CoordinatorEntity, SensorEntity):
    """A sensor that reflects a single value (status or note) for a key."""

    def __init__(self, coordinator, entry_id: str, key: str, value_type: str, entry_type: str = "Cancelation"):
        super().__init__(coordinator)
        self.coordinator = coordinator
        self._entry_id = entry_id
        self._key = key
        self._value_type = value_type
        self._entry_type = entry_type

    @property
    def name(self) -> str:
        # include the type in the friendly name so entity_id will include it
        return f"SCSTC {self._entry_type} {self._key} {self._value_type}"

    @property
    def unique_id(self) -> str:
        return f"scstc_{self._entry_id}_{self._entry_type}_{self._key}_{self._value_type}"

    @property
    def state(self) -> Any:
        return self.coordinator.data.get(self._key, {}).get(self._value_type)

    @property
    def extra_state_attributes(self) -> dict:
        # expose the entire object under the key as attributes
        return self.coordinator.data.get(self._key, {})
