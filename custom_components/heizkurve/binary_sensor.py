"""Binary sensors of the Heizkurve integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_COMPRESSOR
from .coordinator import HeizkurveConfigEntry, HeizkurveData
from .entity import HeizkurveEntity


@dataclass(frozen=True, kw_only=True)
class HeizkurveBinaryDescription(BinarySensorEntityDescription):
    """Binary sensor with a value function and an optional required source."""

    value_fn: Callable[[HeizkurveData], bool | None]
    attrs_fn: Callable[[HeizkurveData], dict[str, Any]] | None = None
    requires: str | None = None


BINARY_SENSORS: tuple[HeizkurveBinaryDescription, ...] = (
    HeizkurveBinaryDescription(
        key="heating_demand",
        value_fn=lambda d: d.heating_demand,
        device_class=BinarySensorDeviceClass.HEAT,
    ),
    HeizkurveBinaryDescription(
        key="fault",
        value_fn=lambda d: d.fault,
        device_class=BinarySensorDeviceClass.PROBLEM,
        attrs_fn=lambda d: {"wert": d.setpoint},
    ),
    HeizkurveBinaryDescription(
        key="compressor_heating",
        value_fn=lambda d: d.compressor_heating,
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        requires=CONF_COMPRESSOR,
    ),
    HeizkurveBinaryDescription(
        key="cycling_lock",
        value_fn=lambda d: d.lock_active,
        attrs_fn=lambda d: {
            "ende": d.lock_until.isoformat() if d.lock_until else None,
            "starts_60min": d.starts_60min,
            "sperren_heute": d.locks_today,
        },
        requires=CONF_COMPRESSOR,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeizkurveConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the binary sensors whose sources are configured."""
    coordinator = entry.runtime_data
    async_add_entities(
        HeizkurveBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if description.requires is None or coordinator.has(description.requires)
    )


class HeizkurveBinarySensor(HeizkurveEntity, BinarySensorEntity):
    """A computed on/off state of the heating curve."""

    entity_description: HeizkurveBinaryDescription

    def __init__(self, coordinator, description: HeizkurveBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
