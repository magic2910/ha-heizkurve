"""Config flow and runtime tests in a real Home Assistant instance."""

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant, ServiceResponse, SupportsResponse
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.heizkurve.const import (
    CONF_ABS_MAX_FLOW,
    CONF_ABS_MIN_FLOW,
    CONF_COMPARISON,
    CONF_COMPRESSOR,
    CONF_INITIAL,
    CONF_MODE,
    CONF_MODE_DHW,
    CONF_OUTDOOR,
    CONF_OUTDOOR_FALLBACK,
    CONF_PV_FORECAST,
    CONF_ROOM,
    CONF_TARGET,
    CONF_WEATHER,
    DOMAIN,
)

TEMP = {"unit_of_measurement": "°C", "device_class": "temperature"}


def _entity(hass: HomeAssistant, key: str) -> str:
    registry = er.async_get(hass)
    for entry in registry.entities.values():
        if entry.platform == DOMAIN and entry.unique_id.split("_", 1)[1] == key:
            return entry.entity_id
    raise AssertionError(f"no entity for {key}")


async def test_config_flow_takes_over_package_values(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.station", "5.0", TEMP)
    hass.states.async_set("input_number.heizkurve_v2_steigung", "0.3")
    hass.states.async_set("input_number.heizkurve_v2_niveau", "-0.5")
    hass.states.async_set("input_number.heizkurve_v2_i_anteil", "0.12")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Heizkurve", CONF_OUTDOOR: "sensor.station"}
    )
    assert result["step_id"] == "forecast"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "plant"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ABS_MIN_FLOW: 30, CONF_ABS_MAX_FLOW: 30}
    )
    assert result["errors"] == {"base": "flow_limits"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ABS_MIN_FLOW: 25, CONF_ABS_MAX_FLOW: 45}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_INITIAL] == {
        "slope": 0.3,
        "level": -0.5,
        "integral": 0.12,
    }
    await hass.async_block_till_done()

    # Only the outdoor sensor configured: pure outdoor curve with own target.
    # 21 + 0.3 * (21 - 5) - 0.5 = 25.3
    setpoint = hass.states.get(_entity(hass, "flow_setpoint"))
    assert float(setpoint.state) == 25.3
    assert hass.states.get(_entity(hass, "target_temperature")) is not None
    registry = er.async_get(hass)
    keys = {e.unique_id.split("_", 1)[1] for e in registry.entities.values()
            if e.platform == DOMAIN}
    assert "integral" not in keys
    assert "room_factor" not in keys
    assert "cycling_lock" not in keys


@pytest.fixture
def full_entry(hass: HomeAssistant) -> MockConfigEntry:
    hass.states.async_set("sensor.station", "unavailable", TEMP)
    hass.states.async_set("sensor.hp_outdoor", "10.7", TEMP)
    hass.states.async_set("sensor.room_a", "23.0", TEMP)
    hass.states.async_set("sensor.room_b", "23.54", TEMP)
    hass.states.async_set("input_number.target", "23.0")
    hass.states.async_set("binary_sensor.compressor", "off")
    hass.states.async_set("sensor.mode", "Heizen")
    hass.states.async_set("sensor.old_curve", "24.5", TEMP)
    return MockConfigEntry(
        domain=DOMAIN,
        title="Heizkurve",
        data={
            CONF_OUTDOOR: "sensor.station",
            CONF_OUTDOOR_FALLBACK: "sensor.hp_outdoor",
            CONF_ROOM: ["sensor.room_a", "sensor.room_b"],
            CONF_TARGET: "input_number.target",
            CONF_ABS_MIN_FLOW: 25,
            CONF_ABS_MAX_FLOW: 45,
            CONF_COMPRESSOR: "binary_sensor.compressor",
            CONF_MODE: "sensor.mode",
            CONF_MODE_DHW: "Warmwasserbereitung",
            CONF_COMPARISON: "sensor.old_curve",
            CONF_INITIAL: {"slope": 0.3, "level": -0.5, "integral": 0.12},
        },
    )


async def test_full_setup_values(hass: HomeAssistant, full_entry) -> None:
    full_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()

    # Fallback sensor used; room average 23.27; I-term not used while inactive.
    # 23 + 0.3 * 12.3 - 0.5 - 0.27 = 25.92
    state = hass.states.get(_entity(hass, "flow_setpoint"))
    assert float(state.state) == 25.9
    assert state.attributes["aussen_quelle"] == "sensor.hp_outdoor"
    assert state.attributes["i_anteil"] == 0
    assert float(hass.states.get(_entity(hass, "integral")).state) == 0.12
    assert float(hass.states.get(_entity(hass, "comparison_difference")).state) == 1.4

    # Switching on takes the I-term into the setpoint.
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": _entity(hass, "active")}, blocking=True
    )
    state = hass.states.get(_entity(hass, "flow_setpoint"))
    assert float(state.state) == 26.0
    assert state.attributes["i_anteil"] == 0.12

    # Switching off resets the I-term like the package does.
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": _entity(hass, "active")}, blocking=True
    )
    assert float(hass.states.get(_entity(hass, "integral")).state) == 0

    # Changing a parameter recomputes at once.
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": _entity(hass, "slope"), "value": 0.5},
        blocking=True,
    )
    state = hass.states.get(_entity(hass, "flow_setpoint"))
    assert float(state.state) == round(23 + 0.5 * 12.3 - 0.5 - 0.27, 1)


async def test_integral_runs_only_when_active(hass: HomeAssistant, full_entry) -> None:
    hass.states.async_set("sensor.room_a", "22.0", TEMP)
    hass.states.async_set("sensor.room_b", "22.0", TEMP)
    full_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = full_entry.runtime_data

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=11))
    await hass.async_block_till_done()
    assert coordinator.integral == 0.12

    coordinator.active = True
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=22))
    await hass.async_block_till_done()
    # error 1 K, 10 min, tau 24 h: + 0.007
    assert coordinator.integral == pytest.approx(0.127)


async def test_cycling_lock_and_dhw_excluded(
    hass: HomeAssistant, full_entry, freezer
) -> None:
    full_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = full_entry.runtime_data
    coordinator.active = True
    coordinator.lock_enabled = True
    lock = _entity(hass, "cycling_lock")
    starts = _entity(hass, "starts_60min")

    async def cycle(minutes: int, mode: str = "Heizen") -> None:
        hass.states.async_set("sensor.mode", mode)
        hass.states.async_set("binary_sensor.compressor", "on")
        await hass.async_block_till_done()
        freezer.tick(timedelta(minutes=minutes))
        hass.states.async_set("binary_sensor.compressor", "off")
        await hass.async_block_till_done()
        freezer.tick(timedelta(minutes=5))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()

    await cycle(5, mode="Warmwasserbereitung")
    assert hass.states.get(starts).state == "0"
    await cycle(5)
    await cycle(5)
    assert hass.states.get(lock).state == "off"
    await cycle(5)
    assert hass.states.get(starts).state == "3"
    assert hass.states.get(lock).state == "on"
    assert hass.states.get(_entity(hass, "locks_today")).state == "1"

    # The lock ends when the house gets too cold (23 - 0.5 - 0.5).
    hass.states.async_set("sensor.room_a", "21.9", TEMP)
    hass.states.async_set("sensor.room_b", "21.9", TEMP)
    await hass.async_block_till_done()
    assert hass.states.get(lock).state == "off"


async def test_fault_after_five_minutes(
    hass: HomeAssistant, full_entry, freezer
) -> None:
    full_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()
    fault = _entity(hass, "fault")
    assert hass.states.get(fault).state == "off"

    hass.states.async_set("sensor.hp_outdoor", "unavailable", TEMP)
    await hass.async_block_till_done()
    assert hass.states.get(_entity(hass, "flow_setpoint")).state == "unavailable"
    assert hass.states.get(fault).state == "off"

    freezer.tick(timedelta(minutes=6))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(fault).state == "on"


async def test_forecast_from_weather_entity(hass: HomeAssistant, full_entry) -> None:
    now = dt_util.utcnow()
    calls: list[str] = []

    async def get_forecasts(call) -> ServiceResponse:
        entity_id = call.data["entity_id"]
        entity_id = entity_id[0] if isinstance(entity_id, list) else entity_id
        calls.append(entity_id)
        if entity_id == "weather.primary":
            return {entity_id: {"forecast": []}}
        return {
            entity_id: {
                "forecast": [
                    {"datetime": (now + timedelta(hours=h)).isoformat(),
                     "temperature": 4.7}
                    for h in range(0, 50)
                ]
            }
        }

    # Replace the weather integration's service with a fake one.
    assert await async_setup_component(hass, "weather", {})
    hass.services.async_register(
        "weather", "get_forecasts", get_forecasts,
        supports_response=SupportsResponse.ONLY,
    )
    full_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        full_entry,
        data={**full_entry.data, CONF_WEATHER: ["weather.primary", "weather.backup"],
              CONF_INITIAL: {"slope": 0.3, "level": -0.5, "forecast_weight": 0.5}},
    )
    await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()

    assert calls == ["weather.primary", "weather.backup"]
    forecast = hass.states.get(_entity(hass, "forecast"))
    assert float(forecast.state) == 4.7
    assert forecast.attributes["quelle"] == "weather.backup"
    # T_eff = 0.5 * 10.7 + 0.5 * 5.7 (limited to 10.7 - 5) = 8.2
    assert float(hass.states.get(_entity(hass, "outdoor_effective")).state) == 8.2
    assert hass.states.get(_entity(hass, "heating_demand")).state == "on"


async def test_solar_deduction_from_helios(hass: HomeAssistant, full_entry) -> None:
    start = dt_util.now().replace(minute=0, second=0, microsecond=0)
    forecast = [
        {"datetime": (start + timedelta(minutes=15 * i)).isoformat(),
         "watts": 2000, "p10": None, "p90": None}
        for i in range(-4, 4 * 48)
    ]
    hass.states.async_set("sensor.pv_power_now", "2000", {"forecast": forecast})
    full_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        full_entry, data={**full_entry.data, CONF_PV_FORECAST: "sensor.pv_power_now"}
    )
    await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()

    # 2 kW over the 8 h horizon = 16 kWh; 1 K * 16 / 20 = 0.8 K
    assert float(hass.states.get(_entity(hass, "solar_forecast")).state) == 16.0
    assert float(hass.states.get(_entity(hass, "solar_deduction")).state) == 0.8
    # 25.92 - 0.8 = 25.12
    assert float(hass.states.get(_entity(hass, "flow_setpoint")).state) == 25.1


async def test_options_flow_can_remove_a_source(hass: HomeAssistant, full_entry) -> None:
    full_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(full_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(full_entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_OUTDOOR: "sensor.hp_outdoor", CONF_TARGET: "input_number.target"},
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ABS_MIN_FLOW: 25, CONF_ABS_MAX_FLOW: 45}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    coordinator = full_entry.runtime_data
    assert not coordinator.has(CONF_ROOM)
    assert not coordinator.has(CONF_COMPRESSOR)
    # 23 + 0.3 * 12.3 - 0.5, no room correction any more
    state = hass.states.get(_entity(hass, "flow_setpoint"))
    assert float(state.state) == round(23 + 0.3 * 12.3 - 0.5, 1)
