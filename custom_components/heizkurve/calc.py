"""Pure calculation logic of the heating curve.

No Home Assistant imports: everything here is unit-testable on its own and
mirrors the template logic of the Heizkurve v2 YAML package.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# Hysteresis around the heating limit (K), as in the package.
HEATING_LIMIT_HYSTERESIS = 0.5
# Tolerance when judging whether a setpoint lies inside min/max (K).
SETPOINT_TOLERANCE = 0.05
# Extra margin below "target - comfort band" that ends a cycling lock early (K).
LOCK_COLD_MARGIN = 0.5


@dataclass(frozen=True)
class CurveParams:
    """Tuning parameters of the curve."""

    slope: float = 0.30
    level: float = -0.5
    room_factor: float = 1.0
    min_flow: float = 25.0
    max_flow: float = 35.0
    forecast_weight: float = 0.0
    forecast_max_deviation: float = 5.0
    solar_max_deduction: float = 0.0
    solar_reference: float = 20.0


@dataclass(frozen=True)
class ForecastStats:
    """Mean of the hourly forecast over the horizon and over 48 h."""

    mean: float | None
    mean_48h: float | None
    min_48h: float | None
    max_48h: float | None
    hours: int


@dataclass(frozen=True)
class FlowResult:
    """Flow setpoint plus the parts it is made of."""

    setpoint: float
    unclamped: float
    without_forecast: float
    room_correction: float
    solar_deduction: float
    integral: float
    min_flow: float
    max_flow: float


def effective_min_flow(min_flow: float, absolute_min: float) -> float:
    """Lower flow limit that never goes below the plant limit."""
    return max(min_flow, absolute_min)


def forecast_stats(
    forecast: Iterable[tuple[datetime, float]], now: datetime, horizon_h: int
) -> ForecastStats:
    """Average the hourly forecast like the package's trigger template."""
    horizon: list[float] = []
    two_days: list[float] = []
    for when, temp in forecast:
        if when <= now - timedelta(hours=1):
            continue
        if when <= now + timedelta(hours=horizon_h):
            horizon.append(temp)
        if when <= now + timedelta(hours=48):
            two_days.append(temp)
    return ForecastStats(
        mean=round(sum(horizon) / len(horizon), 1) if horizon else None,
        mean_48h=round(sum(two_days) / len(two_days), 1) if two_days else None,
        min_48h=min(two_days) if two_days else None,
        max_48h=max(two_days) if two_days else None,
        hours=len(horizon),
    )


def effective_outdoor(
    t_now: float, forecast_mean: float | None, weight: float, max_deviation: float
) -> float:
    """Blend measured and forecast outdoor temperature.

    The forecast is limited to t_now +/- max_deviation first.
    """
    if forecast_mean is None:
        return t_now
    limited = min(max(forecast_mean, t_now - max_deviation), t_now + max_deviation)
    return round((1 - weight) * t_now + weight * limited, 1)


def solar_energy(
    periods: Iterable[tuple[datetime, float]], now: datetime, horizon_h: int
) -> float:
    """PV energy (kWh) over the horizon from Solcast half-hour periods (kW)."""
    kwh = 0.0
    start = now - timedelta(minutes=30)
    end = now + timedelta(hours=horizon_h)
    for period_start, pv_kw in periods:
        if start <= period_start < end:
            kwh += pv_kw * 0.5
    return round(kwh, 1)


def solar_deduction(kwh: float, reference: float, max_deduction: float) -> float:
    """Flow deduction (K) for expected solar gains."""
    if reference <= 0:
        return 0.0
    return round(max_deduction * min(kwh / reference, 1), 1)


def flow_setpoint(
    target: float,
    room: float | None,
    t_eff: float,
    t_now: float,
    params: CurveParams,
    absolute_min: float,
    solar: float = 0.0,
    integral: float = 0.0,
) -> FlowResult:
    """Linear heating curve with room correction, solar deduction and I-term.

    Without a room temperature the room correction is 0.
    """
    vmin = effective_min_flow(params.min_flow, absolute_min)
    vmax = params.max_flow
    room_error = (target - room) if room is not None else 0.0
    room_corr = params.room_factor * room_error

    def curve(t_out: float) -> float:
        return target + params.slope * (target - t_out) + params.level + room_corr

    raw = curve(t_eff) - solar + integral
    no_forecast = curve(t_now)
    return FlowResult(
        setpoint=round(min(max(raw, vmin), vmax), 1),
        unclamped=round(raw, 2),
        without_forecast=round(min(max(no_forecast, vmin), vmax), 1),
        room_correction=round(room_corr, 1),
        solar_deduction=solar,
        integral=integral,
        min_flow=vmin,
        max_flow=vmax,
    )


def heating_demand(
    previous: bool | None, reference_temp: float | None, limit: float
) -> bool | None:
    """Heating limit with hysteresis; keeps the previous state inside the band."""
    if reference_temp is None:
        return previous
    if reference_temp < limit - HEATING_LIMIT_HYSTERESIS:
        return True
    if reference_temp > limit + HEATING_LIMIT_HYSTERESIS:
        return False
    return previous


def integral_step(
    i_old: float,
    error: float,
    dt_h: float,
    tau_h: float,
    i_max: float,
    unclamped: float,
    vmin: float,
    vmax: float,
) -> float:
    """One step of the I-term with anti-windup at the flow limits."""
    if tau_h <= 0:
        return i_old
    windup = (unclamped >= vmax and error > 0) or (unclamped <= vmin and error < 0)
    i_new = i_old if windup else i_old + error * dt_h / tau_h
    return round(min(max(i_new, -i_max), i_max), 3)


def comfort_deviation(room: float, target: float, band: float) -> float:
    """Room deviation from target outside the comfort band (K)."""
    return round(max(abs(room - target) - band, 0), 2)


def heating_degree_load(limit: float, t_out: float) -> float:
    """Distance of the outdoor temperature below the heating limit (K)."""
    return round(max(limit - t_out, 0), 2)


def setpoint_valid(value: float | None, vmin: float, vmax: float) -> bool:
    """Whether a setpoint may be written to the heat pump."""
    if value is None:
        return False
    return vmin - SETPOINT_TOLERANCE <= value <= vmax + SETPOINT_TOLERANCE


@dataclass
class DelayedFlag:
    """Boolean that switches only after the raw value held for a delay."""

    delay: timedelta
    state: bool = False
    _pending: bool | None = None
    _since: datetime | None = None

    def update(self, raw: bool, now: datetime) -> bool:
        """Feed the raw value; return the debounced state."""
        if raw == self.state:
            self._pending = None
            self._since = None
            return self.state
        if self._pending != raw:
            self._pending = raw
            self._since = now
        if self._since is not None and now - self._since >= self.delay:
            self.state = raw
            self._pending = None
            self._since = None
        return self.state


@dataclass
class CompressorTracker:
    """Compressor runs for space heating, with an off-delay.

    Short gaps (defrost, CAN dropouts) shorter than off_delay do not count as
    a new start, like delay_off on the package's template binary sensor.
    """

    off_delay: timedelta = timedelta(minutes=3)
    running: bool = False
    starts: list[datetime] = field(default_factory=list)
    run_since: datetime | None = None
    runtime_today: timedelta = timedelta()
    day: str | None = None
    _off_since: datetime | None = None

    def _roll_day(self, now: datetime) -> None:
        today = now.date().isoformat()
        if self.day != today:
            self.day = today
            self.runtime_today = timedelta()
            if self.run_since is not None:
                self.run_since = max(
                    self.run_since,
                    now.replace(hour=0, minute=0, second=0, microsecond=0),
                )

    def update(self, heating: bool, now: datetime) -> None:
        """Feed the raw state (compressor on and not hot water)."""
        self._roll_day(now)
        if heating:
            self._off_since = None
            if not self.running:
                self.running = True
                self.run_since = now
                self.starts.append(now)
            return
        if not self.running:
            return
        if self._off_since is None:
            self._off_since = now
        if now - self._off_since >= self.off_delay:
            self.running = False
            if self.run_since is not None:
                self.runtime_today += self._off_since - self.run_since
            self.run_since = None
            self._off_since = None

    def starts_within(self, now: datetime, window: timedelta) -> int:
        """Number of starts within the window before now."""
        self.starts = [s for s in self.starts if now - s <= timedelta(hours=25)]
        return sum(1 for s in self.starts if now - s <= window)

    def starts_today(self, now: datetime) -> int:
        """Number of starts since midnight."""
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return sum(1 for s in self.starts if s >= midnight)

    def runtime(self, now: datetime) -> timedelta:
        """Runtime since midnight including the current run."""
        self._roll_day(now)
        total = self.runtime_today
        if self.running and self.run_since is not None:
            total += now - self.run_since
        return total


@dataclass(frozen=True)
class LockParams:
    """Parameters of the cycling lock."""

    starts_per_hour: int = 3
    pause: timedelta = timedelta(minutes=60)
    max_per_day: int = 4


def lock_should_start(
    *,
    starts_60min: int,
    params: LockParams,
    locks_today: int,
    room: float | None,
    target: float,
    band: float,
) -> bool:
    """Start a cycling lock: compressor cycles and the house is warm enough."""
    if starts_60min < params.starts_per_hour:
        return False
    if locks_today >= params.max_per_day:
        return False
    if room is not None and room < target - band:
        return False
    return True


def lock_should_end_early(room: float | None, target: float, band: float) -> bool:
    """End a running lock because the house got too cold."""
    return room is not None and room < target - band - LOCK_COLD_MARGIN
