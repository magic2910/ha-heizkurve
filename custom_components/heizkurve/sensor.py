"""Sensors of the Heizkurve integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_COMPARISON,
    CONF_COMPRESSOR,
    CONF_HEAT_METER,
    CONF_PV_FORECAST,
    CONF_ROOM,
    CONF_WEATHER,
)
from .coordinator import HeizkurveConfigEntry, HeizkurveData
from .entity import HeizkurveEntity

TEMP = UnitOfTemperature.CELSIUS


@dataclass(frozen=True, kw_only=True)
class HeizkurveSensorDescription(SensorEntityDescription):
    """Sensor with a value function and an optional required source."""

    value_fn: Callable[[HeizkurveData], Any]
    attrs_fn: Callable[[HeizkurveData], dict[str, Any]] | None = None
    requires: str | None = None


def _temp(key: str, fn: Callable[[HeizkurveData], Any], **kw: Any):
    return HeizkurveSensorDescription(
        key=key,
        value_fn=fn,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=TEMP,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        **kw,
    )


def _kelvin(key: str, fn: Callable[[HeizkurveData], Any], **kw: Any):
    return HeizkurveSensorDescription(
        key=key,
        value_fn=fn,
        native_unit_of_measurement="K",
        state_class=SensorStateClass.MEASUREMENT,
        **kw,
    )


SENSORS: tuple[HeizkurveSensorDescription, ...] = (
    _temp("flow_setpoint", lambda d: d.setpoint, attrs_fn=lambda d: d.attributes,
          icon="mdi:chart-bell-curve-cumulative"),
    _temp("outdoor", lambda d: d.outdoor,
          attrs_fn=lambda d: {"quelle": d.outdoor_source},
          entity_category=EntityCategory.DIAGNOSTIC),
    _temp("outdoor_effective", lambda d: d.outdoor_effective,
          entity_category=EntityCategory.DIAGNOSTIC),
    _temp("room", lambda d: d.room, requires=CONF_ROOM,
          entity_category=EntityCategory.DIAGNOSTIC),
    _temp("forecast", lambda d: d.forecast.mean if d.forecast else None,
          attrs_fn=lambda d: {
              "quelle": d.forecast_source,
              "anzahl_stunden": d.forecast.hours if d.forecast else 0,
          },
          requires=CONF_WEATHER, entity_category=EntityCategory.DIAGNOSTIC),
    _temp("forecast_48h", lambda d: d.forecast.mean_48h if d.forecast else None,
          attrs_fn=lambda d: {
              "min_48h": d.forecast.min_48h if d.forecast else None,
              "max_48h": d.forecast.max_48h if d.forecast else None,
          },
          requires=CONF_WEATHER, entity_category=EntityCategory.DIAGNOSTIC),
    HeizkurveSensorDescription(
        key="solar_forecast",
        value_fn=lambda d: d.solar_energy,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        requires=CONF_PV_FORECAST,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    _kelvin("solar_deduction", lambda d: d.solar_deduction,
            requires=CONF_PV_FORECAST, entity_category=EntityCategory.DIAGNOSTIC),
    _kelvin("integral", lambda d: d.integral, requires=CONF_ROOM,
            entity_category=EntityCategory.DIAGNOSTIC, suggested_display_precision=3),
    _kelvin("comfort_deviation", lambda d: d.comfort_deviation, requires=CONF_ROOM),
    HeizkurveSensorDescription(
        key="degree_hours_today",
        value_fn=lambda d: d.degree_hours_today,
        native_unit_of_measurement="Kh",
        state_class=SensorStateClass.TOTAL_INCREASING,
        requires=CONF_ROOM,
    ),
    _kelvin("degree_load", lambda d: d.degree_load),
    HeizkurveSensorDescription(
        key="degree_days_today",
        value_fn=lambda d: d.degree_days_today,
        native_unit_of_measurement="Kd",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    HeizkurveSensorDescription(
        key="heat_today",
        value_fn=lambda d: d.heat_today,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        requires=CONF_HEAT_METER,
    ),
    HeizkurveSensorDescription(
        key="kwh_per_degree_day",
        value_fn=lambda d: d.kwh_per_degree_day,
        native_unit_of_measurement="kWh/Kd",
        state_class=SensorStateClass.MEASUREMENT,
        requires=CONF_HEAT_METER,
    ),
    HeizkurveSensorDescription(
        key="starts_60min",
        value_fn=lambda d: d.starts_60min,
        state_class=SensorStateClass.MEASUREMENT,
        requires=CONF_COMPRESSOR,
        icon="mdi:counter",
    ),
    HeizkurveSensorDescription(
        key="starts_today",
        value_fn=lambda d: d.starts_today,
        state_class=SensorStateClass.TOTAL_INCREASING,
        requires=CONF_COMPRESSOR,
        icon="mdi:counter",
    ),
    HeizkurveSensorDescription(
        key="runtime_today",
        value_fn=lambda d: d.runtime_today_h,
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        requires=CONF_COMPRESSOR,
    ),
    HeizkurveSensorDescription(
        key="locks_today",
        value_fn=lambda d: d.locks_today,
        state_class=SensorStateClass.TOTAL_INCREASING,
        requires=CONF_COMPRESSOR,
        icon="mdi:timer-pause-outline",
    ),
    _kelvin("comparison_difference", lambda d: d.comparison_difference,
            requires=CONF_COMPARISON, icon="mdi:delta"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeizkurveConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the sensors whose sources are configured."""
    coordinator = entry.runtime_data
    async_add_entities(
        HeizkurveSensor(coordinator, description)
        for description in SENSORS
        if description.requires is None or coordinator.has(description.requires)
    )


class HeizkurveSensor(HeizkurveEntity, SensorEntity):
    """A computed value of the heating curve."""

    entity_description: HeizkurveSensorDescription

    def __init__(self, coordinator, description: HeizkurveSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        return super().available and self.native_value is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
