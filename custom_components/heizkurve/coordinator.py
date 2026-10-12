"""Coordinator: reads the sources, keeps the runtime state, runs calc.py."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import calc
from .const import (
    COMPRESSOR_OFF_DELAY,
    CONF_ABS_MIN_FLOW,
    CONF_COMPARISON,
    CONF_COMPRESSOR,
    CONF_HEAT_METER,
    CONF_MODE,
    CONF_MODE_DHW,
    CONF_OUTDOOR,
    CONF_OUTDOOR_FALLBACK,
    CONF_PV_FORECAST,
    CONF_ROOM,
    CONF_TARGET,
    CONF_WEATHER,
    DEFAULT_ABS_MIN_FLOW,
    DEFAULT_MODE_DHW,
    DOMAIN,
    FAULT_DELAY,
    FORECAST_INTERVAL,
    FORECAST_RETRY_INTERVAL,
    INTEGRAL_INTERVAL,
    PARAM_DEFAULTS,
    STARTS_WINDOW,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

type HeizkurveConfigEntry = ConfigEntry[HeizkurveCoordinator]


@dataclass
class HeizkurveData:
    """Everything the entities show."""

    setpoint: float | None = None
    flow: calc.FlowResult | None = None
    outdoor: float | None = None
    outdoor_source: str | None = None
    outdoor_effective: float | None = None
    room: float | None = None
    target: float | None = None
    forecast: calc.ForecastStats | None = None
    forecast_source: str | None = None
    forecast_updated: datetime | None = None
    solar_energy: float | None = None
    solar_deduction: float | None = None
    integral: float = 0.0
    heating_demand: bool | None = None
    fault: bool = False
    comfort_deviation: float | None = None
    degree_load: float | None = None
    degree_hours_today: float = 0.0
    degree_days_today: float = 0.0
    heat_today: float | None = None
    kwh_per_degree_day: float | None = None
    compressor_heating: bool | None = None
    starts_60min: int = 0
    starts_today: int = 0
    runtime_today_h: float = 0.0
    lock_active: bool = False
    lock_until: datetime | None = None
    locks_today: int = 0
    comparison_difference: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


class HeizkurveCoordinator(DataUpdateCoordinator[HeizkurveData]):
    """Computes the flow setpoint and owns the runtime state."""

    config_entry: HeizkurveConfigEntry

    def __init__(self, hass: HomeAssistant, entry: HeizkurveConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
            always_update=True,
        )
        self.conf: dict[str, Any] = {**entry.data, **entry.options}
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.params: dict[str, float] = dict(PARAM_DEFAULTS)
        self.active = False
        self.lock_enabled = False
        self.integral = 0.0
        self._demand: bool | None = None
        self._lock_until: datetime | None = None
        self._locks: list[datetime] = []
        self._forecast: list[tuple[datetime, float]] = []
        self._forecast_source: str | None = None
        self._forecast_updated: datetime | None = None
        self._fault = calc.DelayedFlag(FAULT_DELAY)
        self._compressor = calc.CompressorTracker(off_delay=COMPRESSOR_OFF_DELAY)
        self._kpi_day: str | None = None
        self._degree_hours = 0.0
        self._degree_days = 0.0
        self._heat_start: float | None = None
        self._last_compute: datetime | None = None

    # ----- configuration helpers -----

    def has(self, key: str) -> bool:
        """Whether an optional source is configured."""
        return bool(self.conf.get(key))

    @property
    def absolute_min_flow(self) -> float:
        return float(self.conf.get(CONF_ABS_MIN_FLOW, DEFAULT_ABS_MIN_FLOW))

    def _source_entities(self) -> list[str]:
        ids: list[str] = []
        for key in (
            CONF_OUTDOOR,
            CONF_OUTDOOR_FALLBACK,
            CONF_TARGET,
            CONF_PV_FORECAST,
            CONF_COMPRESSOR,
            CONF_MODE,
            CONF_HEAT_METER,
            CONF_COMPARISON,
        ):
            if value := self.conf.get(key):
                ids.append(value)
        ids.extend(self.conf.get(CONF_ROOM) or [])
        return ids

    # ----- setup and persistence -----

    async def async_setup(self) -> None:
        """Load the stored state and subscribe to the sources."""
        stored = await self._store.async_load()
        if stored is not None:
            self._restore(stored)

        entry = self.config_entry
        entry.async_on_unload(
            async_track_state_change_event(
                self.hass, self._source_entities(), self._handle_source_change
            )
        )
        entry.async_on_unload(
            async_track_time_interval(
                self.hass, self._async_forecast_tick, FORECAST_INTERVAL
            )
        )
        entry.async_on_unload(
            async_track_time_interval(
                self.hass, self._async_forecast_retry, FORECAST_RETRY_INTERVAL
            )
        )
        entry.async_on_unload(
            async_track_time_interval(
                self.hass, self._async_integral_tick, INTEGRAL_INTERVAL
            )
        )
        await self.async_update_forecast()

    def _restore(self, stored: dict[str, Any]) -> None:
        self.params.update(
            {k: float(v) for k, v in stored.get("params", {}).items()
             if k in self.params}
        )
        self.active = bool(stored.get("active", False))
        self.lock_enabled = bool(stored.get("lock_enabled", False))
        self.integral = float(stored.get("integral", 0.0))
        self._demand = stored.get("demand")
        self._lock_until = _parse(stored.get("lock_until"))
        self._locks = [d for d in map(_parse, stored.get("locks", [])) if d]
        self._kpi_day = stored.get("kpi_day")
        self._degree_hours = float(stored.get("degree_hours", 0.0))
        self._degree_days = float(stored.get("degree_days", 0.0))
        self._heat_start = stored.get("heat_start")
        comp = stored.get("compressor", {})
        self._compressor.starts = [
            d for d in map(_parse, comp.get("starts", [])) if d
        ]
        self._compressor.day = comp.get("day")
        self._compressor.runtime_today = timedelta(
            seconds=float(comp.get("runtime_today_s", 0))
        )

    def _serialize(self) -> dict[str, Any]:
        return {
            "params": self.params,
            "active": self.active,
            "lock_enabled": self.lock_enabled,
            "integral": self.integral,
            "demand": self._demand,
            "lock_until": _iso(self._lock_until),
            "locks": [_iso(d) for d in self._locks],
            "kpi_day": self._kpi_day,
            "degree_hours": self._degree_hours,
            "degree_days": self._degree_days,
            "heat_start": self._heat_start,
            "compressor": {
                "starts": [_iso(d) for d in self._compressor.starts],
                "day": self._compressor.day,
                "runtime_today_s": self._compressor.runtime_today.total_seconds(),
            },
        }

    def _save(self) -> None:
        self._store.async_delay_save(self._serialize, 10)

    # ----- user actions -----

    async def async_set_param(self, key: str, value: float) -> None:
        self.params[key] = value
        if key == "integral_time" and value < 0.5:
            self.integral = 0.0
        self._save()
        self.async_set_updated_data(self._compute())

    async def async_set_active(self, on: bool) -> None:
        self.active = on
        if not on:
            # The I-term starts from zero after switching off.
            self.integral = 0.0
        self._save()
        self.async_set_updated_data(self._compute())

    async def async_set_lock_enabled(self, on: bool) -> None:
        self.lock_enabled = on
        self._save()
        self.async_set_updated_data(self._compute())

    async def async_reset_integral(self) -> None:
        self.integral = 0.0
        self._save()
        self.async_set_updated_data(self._compute())

    # ----- events -----

    @callback
    def _handle_source_change(self, event: Event[EventStateChangedData]) -> None:
        self.async_set_updated_data(self._compute())

    async def _async_forecast_tick(self, _now: datetime) -> None:
        await self.async_update_forecast()
        self.async_set_updated_data(self._compute())

    async def _async_forecast_retry(self, now: datetime) -> None:
        """Ask again every minute while no forecast is available."""
        if self.has(CONF_WEATHER) and not self._forecast:
            await self._async_forecast_tick(now)

    async def _async_update_data(self) -> HeizkurveData:
        return self._compute()

    async def async_update_forecast(self) -> None:
        """Fetch the hourly forecast from the first weather entity that has one."""
        for entity_id in self.conf.get(CONF_WEATHER) or []:
            try:
                response = await self.hass.services.async_call(
                    "weather",
                    "get_forecasts",
                    {"entity_id": entity_id, "type": "hourly"},
                    blocking=True,
                    return_response=True,
                )
            except HomeAssistantError as err:
                _LOGGER.debug("Forecast from %s failed: %s", entity_id, err)
                continue
            items = (response or {}).get(entity_id, {}).get("forecast") or []
            forecast = _parse_forecast(items)
            if forecast:
                self._forecast = forecast
                self._forecast_source = entity_id
                self._forecast_updated = dt_util.utcnow()
                return
        if self.has(CONF_WEATHER):
            self._forecast = []
            self._forecast_source = None

    async def _async_integral_tick(self, _now: datetime) -> None:
        """Advance the I-term every 10 minutes (only while active)."""
        data = self.data
        if data is None or data.flow is None:
            return
        tau = self.params["integral_time"]
        if tau < 0.5:
            self.integral = 0.0
            return
        if not (
            self.active
            and data.heating_demand
            and not data.lock_active
            and data.room is not None
            and data.target is not None
        ):
            return
        self.integral = calc.integral_step(
            self.integral,
            data.target - data.room,
            INTEGRAL_INTERVAL.total_seconds() / 3600,
            tau,
            self.params["integral_max"],
            data.flow.unclamped,
            data.flow.min_flow,
            data.flow.max_flow,
        )
        self._save()
        self.async_set_updated_data(self._compute())

    # ----- reading sources -----

    def _float(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        try:
            return float(state.state)
        except ValueError:
            return None

    def _room(self) -> float | None:
        values = [
            v for v in (self._float(e) for e in self.conf.get(CONF_ROOM) or [])
            if v is not None
        ]
        return sum(values) / len(values) if values else None

    def _pv_periods(self) -> list[tuple[datetime, float]]:
        """Helios forecast: list of {datetime, watts} in the attribute forecast."""
        periods: list[tuple[datetime, float]] = []
        state = self.hass.states.get(self.conf.get(CONF_PV_FORECAST) or "")
        if state is None:
            return periods
        for item in state.attributes.get("forecast") or []:
            if not isinstance(item, dict):
                continue
            start = item.get("datetime")
            if isinstance(start, str):
                start = dt_util.parse_datetime(start)
            try:
                watts = float(item.get("watts"))
            except (TypeError, ValueError):
                continue
            if isinstance(start, datetime):
                periods.append((dt_util.as_utc(start), watts / 1000))
        return periods

    def _compressor_heating(self) -> bool | None:
        state = self.hass.states.get(self.conf.get(CONF_COMPRESSOR) or "")
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        if state.state != "on":
            return False
        mode = self.hass.states.get(self.conf.get(CONF_MODE) or "")
        dhw = self.conf.get(CONF_MODE_DHW) or DEFAULT_MODE_DHW
        return not (mode is not None and mode.state == dhw)

    # ----- the calculation -----

    def _compute(self) -> HeizkurveData:  # noqa: C901 - one pass over all parts
        now = dt_util.utcnow()
        p = self.params
        data = HeizkurveData(integral=self.integral)

        # Outdoor temperature with fallback.
        data.outdoor = self._float(self.conf.get(CONF_OUTDOOR))
        data.outdoor_source = self.conf.get(CONF_OUTDOOR)
        if data.outdoor is None:
            data.outdoor = self._float(self.conf.get(CONF_OUTDOOR_FALLBACK))
            data.outdoor_source = (
                self.conf.get(CONF_OUTDOOR_FALLBACK) if data.outdoor is not None
                else None
            )

        data.room = self._room() if self.has(CONF_ROOM) else None
        data.target = (
            self._float(self.conf.get(CONF_TARGET))
            if self.has(CONF_TARGET)
            else p["target_temperature"]
        )

        # Forecast.
        if self.has(CONF_WEATHER) and self._forecast:
            data.forecast = calc.forecast_stats(
                self._forecast, now, int(p["forecast_horizon"])
            )
            data.forecast_source = self._forecast_source
            data.forecast_updated = self._forecast_updated

        # Solar.
        if self.has(CONF_PV_FORECAST):
            data.solar_energy = calc.solar_energy(
                self._pv_periods(), now, int(p["forecast_horizon"])
            )
            data.solar_deduction = calc.solar_deduction(
                data.solar_energy, p["solar_reference"], p["solar_max_deduction"]
            )

        # Heating limit: 48 h forecast mean, or the current outdoor temperature
        # when no weather entity is configured.
        if self.has(CONF_WEATHER):
            reference = data.forecast.mean_48h if data.forecast else None
        else:
            reference = data.outdoor
        self._demand = calc.heating_demand(
            self._demand, reference, p["heating_limit"]
        )
        data.heating_demand = self._demand

        curve = calc.CurveParams(
            slope=p["slope"],
            level=p["level"],
            room_factor=p["room_factor"] if self.has(CONF_ROOM) else 0.0,
            min_flow=p["min_flow"],
            max_flow=p["max_flow"],
            forecast_weight=p["forecast_weight"],
            forecast_max_deviation=p["forecast_max_deviation"],
            solar_max_deduction=p["solar_max_deduction"],
            solar_reference=p["solar_reference"],
        )

        if data.outdoor is not None and data.target is not None and (
            not self.has(CONF_ROOM) or data.room is not None
        ):
            data.outdoor_effective = calc.effective_outdoor(
                data.outdoor,
                data.forecast.mean if data.forecast else None,
                curve.forecast_weight,
                curve.forecast_max_deviation,
            )
            data.flow = calc.flow_setpoint(
                target=data.target,
                room=data.room,
                t_eff=data.outdoor_effective,
                t_now=data.outdoor,
                params=curve,
                absolute_min=self.absolute_min_flow,
                solar=data.solar_deduction or 0.0,
                integral=self.integral if self.active else 0.0,
            )
            data.setpoint = data.flow.setpoint

        vmin = calc.effective_min_flow(p["min_flow"], self.absolute_min_flow)
        data.fault = self._fault.update(
            not calc.setpoint_valid(data.setpoint, vmin, p["max_flow"]), now
        )

        self._update_kpis(data, now)
        self._update_compressor_and_lock(data, now)

        if self.has(CONF_COMPARISON) and data.setpoint is not None:
            other = self._float(self.conf.get(CONF_COMPARISON))
            if other is not None:
                data.comparison_difference = round(data.setpoint - other, 1)

        data.attributes = self._attributes(data)
        self._last_compute = now
        self._save()
        return data

    def _update_kpis(self, data: HeizkurveData, now: datetime) -> None:
        today = dt_util.as_local(now).date().isoformat()
        if self._kpi_day != today:
            self._kpi_day = today
            self._degree_hours = 0.0
            self._degree_days = 0.0
            self._heat_start = None
        dt_h = 0.0
        if self._last_compute is not None:
            dt_h = min((now - self._last_compute).total_seconds() / 3600, 0.25)

        p = self.params
        if data.room is not None and data.target is not None:
            data.comfort_deviation = calc.comfort_deviation(
                data.room, data.target, p["comfort_band"]
            )
            self._degree_hours += data.comfort_deviation * dt_h
        if data.outdoor is not None:
            data.degree_load = calc.heating_degree_load(
                p["heating_limit"], data.outdoor
            )
            self._degree_days += data.degree_load * dt_h / 24
        data.degree_hours_today = round(self._degree_hours, 2)
        data.degree_days_today = round(self._degree_days, 3)

        if self.has(CONF_HEAT_METER):
            meter = self._float(self.conf.get(CONF_HEAT_METER))
            if meter is not None:
                if self._heat_start is None or meter < self._heat_start:
                    self._heat_start = meter
                data.heat_today = round(meter - self._heat_start, 2)
                if data.degree_days_today >= 1:
                    data.kwh_per_degree_day = round(
                        data.heat_today / data.degree_days_today, 1
                    )

    def _update_compressor_and_lock(self, data: HeizkurveData, now: datetime) -> None:
        if not self.has(CONF_COMPRESSOR):
            return
        heating = self._compressor_heating()
        if heating is not None:
            self._compressor.update(heating, now)
        data.compressor_heating = self._compressor.running if heating is not None else None
        data.starts_60min = self._compressor.starts_within(now, STARTS_WINDOW)
        data.starts_today = self._compressor.starts_today(dt_util.as_local(now))
        data.runtime_today_h = round(
            self._compressor.runtime(now).total_seconds() / 3600, 2
        )

        midnight = dt_util.start_of_local_day()
        self._locks = [d for d in self._locks if d >= midnight - timedelta(days=1)]
        locks_today = sum(1 for d in self._locks if d >= midnight)
        p = self.params
        band = p["comfort_band"]

        if self._lock_until is not None:
            if (
                now >= self._lock_until
                or not (self.active and self.lock_enabled)
                or (
                    data.target is not None
                    and calc.lock_should_end_early(data.room, data.target, band)
                )
            ):
                self._lock_until = None
        elif (
            self.active
            and self.lock_enabled
            and data.target is not None
            and calc.lock_should_start(
                starts_60min=data.starts_60min,
                params=calc.LockParams(
                    starts_per_hour=int(p["lock_starts"]),
                    pause=timedelta(minutes=p["lock_pause"]),
                    max_per_day=int(p["lock_max_per_day"]),
                ),
                locks_today=locks_today,
                room=data.room,
                target=data.target,
                band=band,
            )
        ):
            self._lock_until = now + timedelta(minutes=p["lock_pause"])
            self._locks.append(now)
            locks_today += 1

        data.lock_active = self._lock_until is not None
        data.lock_until = self._lock_until
        data.locks_today = locks_today

    def _attributes(self, data: HeizkurveData) -> dict[str, Any]:
        flow = data.flow
        if flow is None:
            return {}
        return {
            "vorlauf_ohne_prognose": flow.without_forecast,
            "raumkorrektur": flow.room_correction,
            "solarabzug": flow.solar_deduction,
            "aussen_effektiv": data.outdoor_effective,
            "i_anteil": flow.integral,
            "vorlauf_unbegrenzt": flow.unclamped,
            "aussen_quelle": data.outdoor_source,
            "prognose_quelle": data.forecast_source,
            "prognose_stand": _iso(data.forecast_updated),
        }


def _parse_forecast(items: list[dict[str, Any]]) -> list[tuple[datetime, float]]:
    forecast: list[tuple[datetime, float]] = []
    for item in items:
        when = item.get("datetime")
        temp = item.get("temperature")
        if isinstance(when, str):
            when = dt_util.parse_datetime(when)
        if isinstance(when, datetime) and isinstance(temp, (int, float)):
            forecast.append((dt_util.as_utc(when), float(temp)))
    return forecast


def _parse(value: str | None) -> datetime | None:
    return dt_util.parse_datetime(value) if value else None


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
