"""Switches of the Heizkurve integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_COMPRESSOR
from .coordinator import HeizkurveConfigEntry, HeizkurveCoordinator
from .entity import HeizkurveEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeizkurveConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the active switch and, with a compressor sensor, the lock switch."""
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [ActiveSwitch(coordinator)]
    if coordinator.has(CONF_COMPRESSOR):
        entities.append(LockSwitch(coordinator))
    async_add_entities(entities)


class ActiveSwitch(HeizkurveEntity, SwitchEntity):
    """Heating curve drives the heat pump (I-term runs, blueprint writes)."""

    _attr_icon = "mdi:swap-horizontal"

    def __init__(self, coordinator: HeizkurveCoordinator) -> None:
        super().__init__(coordinator, "active")

    @property
    def is_on(self) -> bool:
        return self.coordinator.active

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_active(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_active(False)


class LockSwitch(HeizkurveEntity, SwitchEntity):
    """Cycling lock armed (only acts together with the active switch)."""

    _attr_icon = "mdi:sine-wave"

    def __init__(self, coordinator: HeizkurveCoordinator) -> None:
        super().__init__(coordinator, "cycling_lock_enabled")

    @property
    def is_on(self) -> bool:
        return self.coordinator.lock_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_lock_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_lock_enabled(False)
