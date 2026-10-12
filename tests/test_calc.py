"""Tests for the pure calculation logic, checked against the YAML package."""

from datetime import datetime, timedelta, timezone

import pytest

from custom_components.heizkurve import calc

NOW = datetime(2026, 10, 12, 9, 0, tzinfo=timezone.utc)
PARAMS = calc.CurveParams(
    slope=0.30,
    level=-0.5,
    room_factor=1.0,
    min_flow=25,
    max_flow=35,
    forecast_weight=0.5,
    forecast_max_deviation=5,
    solar_max_deduction=1,
    solar_reference=20,
)


def test_flow_matches_live_package_value():
    """sensor.heizkurve_v2 on 12.10.2026: unclamped 25.04, setpoint 25.0."""
    result = calc.flow_setpoint(
        target=23.0,
        room=23.27,
        t_eff=10.7,
        t_now=10.7,
        params=PARAMS,
        absolute_min=25,
        solar=1.0,
        integral=0.12,
    )
    assert result.unclamped == pytest.approx(25.04)
    assert result.setpoint == 25.0
    assert result.room_correction == -0.3


def test_flow_is_clamped_and_never_below_absolute_min():
    params = calc.CurveParams(slope=0.3, level=-0.5, min_flow=20, max_flow=35)
    warm = calc.flow_setpoint(23, 23, 20, 20, params, absolute_min=25)
    assert warm.setpoint == 25
    cold = calc.flow_setpoint(23, 21, -30, -30, params, absolute_min=25)
    assert cold.setpoint == 35


def test_flow_without_room_temperature_has_no_room_correction():
    result = calc.flow_setpoint(23, None, 0, 0, PARAMS, absolute_min=25)
    assert result.room_correction == 0
    assert result.unclamped == pytest.approx(23 + 0.3 * 23 - 0.5)


def test_without_forecast_ignores_solar_and_integral():
    result = calc.flow_setpoint(23, 23, 5, 0, PARAMS, 25, solar=1, integral=1)
    assert result.without_forecast == round(23 + 0.3 * 23 - 0.5, 1)


def test_effective_outdoor_limits_forecast():
    assert calc.effective_outdoor(10, None, 0.5, 5) == 10
    assert calc.effective_outdoor(10, 14, 0.5, 5) == 12
    assert calc.effective_outdoor(10, 30, 0.5, 5) == 12.5
    assert calc.effective_outdoor(10, -10, 1.0, 5) == 5


def test_forecast_stats_uses_horizon_and_48h():
    forecast = [(NOW + timedelta(hours=h), float(h)) for h in range(-2, 60)]
    stats = calc.forecast_stats(forecast, NOW, horizon_h=4)
    # hours 0..4 inside the horizon (-1 h excluded: not after now - 1 h)
    assert stats.hours == 5
    assert stats.mean == 2.0
    assert stats.min_48h == 0
    assert stats.max_48h == 48


def test_solar_energy_from_quarter_hour_periods():
    # Helios: 15-min periods in kW (watts / 1000), 2 kW for the whole day
    periods = [(NOW + timedelta(minutes=15 * i), 2.0) for i in range(-8, 40)]
    assert calc.solar_energy(periods, NOW, horizon_h=2) == 4.0
    # a period that started 5 min ago only counts for its remaining 10 min
    late = NOW + timedelta(minutes=5)
    assert calc.solar_energy(periods, late, horizon_h=1) == 2.0
    assert calc.solar_energy([], NOW, horizon_h=2) == 0
    assert calc.solar_deduction(5.0, 20, 1) == 0.2
    assert calc.solar_deduction(50, 20, 1) == 1
    assert calc.solar_deduction(5, 0, 1) == 0


def test_heating_demand_hysteresis():
    assert calc.heating_demand(None, 10, 16) is True
    assert calc.heating_demand(True, 16.3, 16) is True
    assert calc.heating_demand(False, 16.3, 16) is False
    assert calc.heating_demand(True, 16.6, 16) is False
    assert calc.heating_demand(True, None, 16) is True


def test_integral_step_and_anti_windup():
    step = calc.integral_step(0, 0.6, 10 / 60, 24, 2, 26, 25, 35)
    assert step == pytest.approx(round(0.6 * (10 / 60) / 24, 3))
    # at max flow with positive error: frozen
    assert calc.integral_step(0.5, 1, 1 / 6, 24, 2, 35, 25, 35) == 0.5
    # at min flow with negative error: frozen
    assert calc.integral_step(0.5, -1, 1 / 6, 24, 2, 25, 25, 35) == 0.5
    # limited to +/- i_max
    assert calc.integral_step(1.99, 5, 1, 1, 2, 30, 25, 35) == 2
    assert calc.integral_step(0.3, 1, 1, 0, 2, 30, 25, 35) == 0.3


def test_kpis():
    assert calc.comfort_deviation(22.2, 23, 0.5) == 0.3
    assert calc.comfort_deviation(23.2, 23, 0.5) == 0
    assert calc.heating_degree_load(16, 10) == 6
    assert calc.heating_degree_load(16, 18) == 0


def test_setpoint_valid():
    assert calc.setpoint_valid(25, 25, 35)
    assert calc.setpoint_valid(24.96, 25, 35)
    assert not calc.setpoint_valid(24.9, 25, 35)
    assert not calc.setpoint_valid(None, 25, 35)


def test_delayed_flag():
    flag = calc.DelayedFlag(timedelta(minutes=5))
    assert flag.update(True, NOW) is False
    assert flag.update(True, NOW + timedelta(minutes=4)) is False
    assert flag.update(True, NOW + timedelta(minutes=5)) is True
    assert flag.update(False, NOW + timedelta(minutes=6)) is True
    assert flag.update(True, NOW + timedelta(minutes=7)) is True
    assert flag.update(False, NOW + timedelta(minutes=8)) is True
    assert flag.update(False, NOW + timedelta(minutes=13)) is False


def test_compressor_tracker_bridges_short_gaps():
    tracker = calc.CompressorTracker()
    t = NOW
    tracker.update(True, t)
    tracker.update(False, t + timedelta(minutes=10))
    tracker.update(True, t + timedelta(minutes=12))  # 2 min gap: same run
    tracker.update(False, t + timedelta(minutes=20))
    tracker.update(False, t + timedelta(minutes=24))  # off for 4 min: run ends
    tracker.update(True, t + timedelta(minutes=30))
    assert tracker.starts_within(t + timedelta(minutes=31), timedelta(hours=1)) == 2
    assert tracker.runtime(t + timedelta(minutes=31)) == timedelta(minutes=21)


def test_lock_decisions():
    params = calc.LockParams(starts_per_hour=3, max_per_day=4)
    kw = {"params": params, "target": 23, "band": 0.5}
    assert calc.lock_should_start(starts_60min=3, locks_today=0, room=22.8, **kw)
    assert not calc.lock_should_start(starts_60min=2, locks_today=0, room=23, **kw)
    assert not calc.lock_should_start(starts_60min=3, locks_today=4, room=23, **kw)
    assert not calc.lock_should_start(starts_60min=3, locks_today=0, room=22.4, **kw)
    assert calc.lock_should_end_early(21.9, 23, 0.5)
    assert not calc.lock_should_end_early(22.1, 23, 0.5)
