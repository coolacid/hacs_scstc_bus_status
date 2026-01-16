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
    entry_type = entry.data.get("type")

    if entry_type == "Cancelation":
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        data = coordinator.data or {}

        entities: list[CoordinatorEntity] = []

        for key in data.keys():
            # sensor for status
            entities.append(MySensorValue(coordinator, entry.entry_id, key, "status", "Cancelation"))
            # sensor for note
            entities.append(MySensorValue(coordinator, entry.entry_id, key, "note", "Cancelation"))

        async_add_entities(entities, True)
        return

    if entry_type == "Bus":
        # For Bus entries, create sensors based on the keys of the provided last_data dict
        ent_info = hass.data[DOMAIN].get(entry.entry_id)
        if not ent_info:
            return
        last_data = ent_info.get("last_data") or []
        sample = last_data[0] if last_data else {}

        entities: list[CoordinatorEntity] = []

        busnum = str(entry.data.get("bus_number")) if entry.data.get("bus_number") is not None else None

        for field in sample.keys():
            entities.append(BusFieldSensor(hass, entry.entry_id, busnum, field))

        async_add_entities(entities, True)
        return


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


class BusFieldSensor(CoordinatorEntity, SensorEntity):
    """Sensor for a single field from a Bus entry's data."""

    def __init__(self, hass, entry_id: str, bus_number: str, field: str):
        # Bus sensors use the shared bus coordinator
        coordinator = hass.data[DOMAIN].get(entry_id, {}).get("coordinator")
        super().__init__(coordinator)
        self.hass = hass
        self._entry_id = entry_id
        self._bus_number = bus_number
        self._field = field

    @property
    def name(self) -> str:
        return f"SCSTC Bus {self._bus_number} {self._field}"

    @property
    def unique_id(self) -> str:
        return f"scstc_{self._entry_id}_Bus_{self._bus_number}_{self._field}"

    @property
    def state(self):
        ent_info = self.hass.data[DOMAIN].get(self._entry_id, {})
        last_data = ent_info.get("last_data") or []
        value = None
        if last_data:
            first = last_data[0]
            value = first.get(self._field)
            # Convert datetimes to ISO strings for state
            if isinstance(value, (type(__import__("datetime").datetime.now()))):
                try:
                    value = value.isoformat()
                except Exception:
                    value = str(value)
        return value

    @property
    def extra_state_attributes(self) -> dict:
        ent_info = self.hass.data[DOMAIN].get(self._entry_id, {})
        last_data = ent_info.get("last_data") or []
        if last_data:
            return last_data[0]
        return {}
