"""Constants for the Heizkurve integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

DOMAIN = "heizkurve"

# Config entry keys (sources).
CONF_OUTDOOR = "outdoor_sensor"
CONF_OUTDOOR_FALLBACK = "outdoor_fallback_sensor"
CONF_ROOM = "room_sensors"
CONF_TARGET = "target_entity"
CONF_WEATHER = "weather_entities"
CONF_PV_FORECAST = "pv_forecast"
CONF_ABS_MIN_FLOW = "absolute_min_flow"
CONF_ABS_MAX_FLOW = "absolute_max_flow"
CONF_COMPRESSOR = "compressor_sensor"
CONF_MODE = "mode_entity"
CONF_MODE_DHW = "mode_dhw_value"
CONF_HEAT_METER = "heat_meter_sensor"
CONF_COMPARISON = "comparison_sensor"

DEFAULT_ABS_MIN_FLOW = 25.0
DEFAULT_ABS_MAX_FLOW = 45.0
DEFAULT_MODE_DHW = "Warmwasserbereitung"


UPDATE_INTERVAL = timedelta(minutes=1)
FORECAST_INTERVAL = timedelta(minutes=30)
INTEGRAL_INTERVAL = timedelta(minutes=10)
FAULT_DELAY = timedelta(minutes=5)
COMPRESSOR_OFF_DELAY = timedelta(minutes=3)
STARTS_WINDOW = timedelta(minutes=60)

STORAGE_VERSION = 1


@dataclass(frozen=True)
class ParamSpec:
    """A tuning parameter exposed as number entity."""

    key: str
    default: float
    minimum: float
    maximum: float
    step: float
    unit: str | None
    icon: str
    # Which configured source the parameter needs: None = always.
    requires: str | None = None


PARAMS: tuple[ParamSpec, ...] = (
    ParamSpec("slope", 0.30, 0.05, 1.5, 0.01, None, "mdi:chart-line-variant"),
    ParamSpec("level", -0.5, -10, 10, 0.1, "K", "mdi:arrow-up-down"),
    ParamSpec("room_factor", 1.0, 0, 5, 0.1, None, "mdi:home-thermometer",
              requires=CONF_ROOM),
    ParamSpec("min_flow", 25.0, 10, 45, 0.5, "°C", "mdi:thermometer-chevron-down"),
    ParamSpec("max_flow", 35.0, 20, 70, 0.5, "°C", "mdi:thermometer-chevron-up"),
    ParamSpec("heating_limit", 16.0, 10, 22, 0.5, "°C", "mdi:thermometer-lines"),
    ParamSpec("forecast_horizon", 8, 1, 24, 1, "h", "mdi:clock-fast",
              requires=CONF_WEATHER),
    ParamSpec("forecast_weight", 0.5, 0, 1, 0.05, None, "mdi:scale-balance",
              requires=CONF_WEATHER),
    ParamSpec("forecast_max_deviation", 5.0, 0, 15, 0.5, "K",
              "mdi:arrow-expand-vertical", requires=CONF_WEATHER),
    ParamSpec("solar_max_deduction", 1.0, 0, 5, 0.1, "K", "mdi:weather-sunny",
              requires=CONF_PV_FORECAST),
    ParamSpec("solar_reference", 20, 1, 60, 1, "kWh", "mdi:solar-power",
              requires=CONF_PV_FORECAST),
    ParamSpec("integral_time", 24, 0, 72, 1, "h", "mdi:timer-sand",
              requires=CONF_ROOM),
    ParamSpec("integral_max", 2.0, 0, 5, 0.1, "K", "mdi:arrow-collapse-vertical",
              requires=CONF_ROOM),
    ParamSpec("comfort_band", 0.5, 0, 2, 0.1, "K", "mdi:arrow-left-right",
              requires=CONF_ROOM),
    ParamSpec("lock_starts", 3, 2, 10, 1, None, "mdi:counter",
              requires=CONF_COMPRESSOR),
    ParamSpec("lock_pause", 60, 15, 180, 5, "min", "mdi:timer-pause",
              requires=CONF_COMPRESSOR),
    ParamSpec("lock_max_per_day", 4, 1, 10, 1, None, "mdi:numeric",
              requires=CONF_COMPRESSOR),
)

# Target temperature number, only created when no target entity is configured.
TARGET_PARAM = ParamSpec(
    "target_temperature", 21.0, 15, 25, 0.1, "°C", "mdi:thermometer"
)

PARAM_DEFAULTS = {p.key: p.default for p in (*PARAMS, TARGET_PARAM)}
