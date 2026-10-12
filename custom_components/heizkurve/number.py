"""Tuning parameters as number entities."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_ABS_MAX_FLOW,
    CONF_TARGET,
    DEFAULT_ABS_MAX_FLOW,
    PARAMS,
    TARGET_PARAM,
    ParamSpec,
)
from .coordinator import HeizkurveConfigEntry, HeizkurveCoordinator
from .entity import HeizkurveEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeizkurveConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add a number per parameter whose source is configured."""
    coordinator = entry.runtime_data
    specs = [p for p in PARAMS if p.requires is None or coordinator.has(p.requires)]
    entities = [ParamNumber(coordinator, spec) for spec in specs]
    if not coordinator.has(CONF_TARGET):
        target = ParamNumber(coordinator, TARGET_PARAM)
        target._attr_entity_category = None
        entities.append(target)
    async_add_entities(entities)


class ParamNumber(HeizkurveEntity, NumberEntity):
    """One tuning parameter, stored by the coordinator."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: HeizkurveCoordinator, spec: ParamSpec) -> None:
        super().__init__(coordinator, spec.key)
        self._spec = spec
        self._attr_native_step = spec.step
        self._attr_native_unit_of_measurement = spec.unit
        self._attr_icon = spec.icon
        minimum, maximum = spec.minimum, spec.maximum
        # Min/max flow can only move inside the plant limits.
        abs_min = coordinator.absolute_min_flow
        abs_max = float(coordinator.conf.get(CONF_ABS_MAX_FLOW, DEFAULT_ABS_MAX_FLOW))
        if spec.key in ("min_flow", "max_flow"):
            minimum, maximum = abs_min, abs_max
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum

    @property
    def native_value(self) -> float:
        return self.coordinator.params[self._spec.key]

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_param(self._spec.key, value)
