"""Run both blueprints as automations against mocked heat pump entities."""

import shutil
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import async_mock_service

BLUEPRINTS = Path(__file__).parent.parent / "blueprints" / "automation" / "heizkurve"


@pytest.fixture(autouse=True)
def install_blueprints(hass: HomeAssistant) -> None:
    target = Path(hass.config.path("blueprints/automation/heizkurve"))
    target.mkdir(parents=True, exist_ok=True)
    for path in BLUEPRINTS.glob("*.yaml"):
        shutil.copy(path, target / path.name)


async def _setup(hass: HomeAssistant, blueprint: str, inputs: dict) -> None:
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "id": "test",
                "alias": "test",
                "use_blueprint": {
                    "path": f"heizkurve/{blueprint}",
                    "input": inputs,
                },
            }
        },
    )
    await hass.async_block_till_done()


WRITE_INPUTS = {
    "setpoint": "sensor.heizkurve_flow_setpoint",
    "active_switch": "switch.heizkurve_active",
    "targets": ["number.vl_tag", "number.vl_nacht", "number.vl_extra"],
    "mode_select": "select.hk_funktion",
    "fault_sensor": "binary_sensor.heizkurve_fault",
    "notify_action": "notify.phone",
    "heating_demand": "binary_sensor.heizkurve_heating_demand",
    "operating_mode_select": "select.betriebsmodus",
}


def _heat_pump(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.heizkurve_flow_setpoint", "26.3")
    hass.states.async_set("switch.heizkurve_active", "off")
    hass.states.async_set("number.vl_tag", "26.2", {"min": 20, "max": 90})
    hass.states.async_set("number.vl_nacht", "25.0", {"min": 10, "max": 90})
    hass.states.async_set("number.vl_extra", "26.3", {"min": 20, "max": 90})
    hass.states.async_set("select.hk_funktion", "Witterungsgeführt")
    hass.states.async_set("binary_sensor.heizkurve_fault", "off")
    hass.states.async_set("binary_sensor.heizkurve_heating_demand", "on")
    hass.states.async_set("select.betriebsmodus", "Heizen")


async def test_write_blueprint(hass: HomeAssistant) -> None:
    _heat_pump(hass)
    numbers = async_mock_service(hass, "number", "set_value")
    selects = async_mock_service(hass, "select", "select_option")
    notify = async_mock_service(hass, "notify", "phone")
    await _setup(hass, "vorlauf_schreiben.yaml", WRITE_INPUTS)

    # Inactive: nothing is written.
    hass.states.async_set("binary_sensor.heizkurve_heating_demand", "off")
    await hass.async_block_till_done()
    assert numbers == [] and selects == []

    # Switching on: mode to "Fest", only the values that differ >= 0.3 K
    # (default): vl_tag is 0.2 K off and stays, vl_extra is exactly 0.3 K off.
    hass.states.async_set("number.vl_tag", "26.1", {"min": 20, "max": 90})
    hass.states.async_set("number.vl_extra", "26.0", {"min": 20, "max": 90})
    hass.states.async_set("switch.heizkurve_active", "on")
    await hass.async_block_till_done()
    assert [c.data["option"] for c in selects] == ["Fest"]
    assert [(c.data["entity_id"], c.data["value"]) for c in numbers] == [
        (["number.vl_nacht"], 26.3),
        (["number.vl_extra"], 26.3),
    ]

    # Heating demand gone while active: operating mode to summer.
    hass.states.async_set("binary_sensor.heizkurve_heating_demand", "on")
    await hass.async_block_till_done()
    hass.states.async_set("binary_sensor.heizkurve_heating_demand", "off")
    await hass.async_block_till_done()
    assert selects[-1].data == {"entity_id": ["select.betriebsmodus"], "option": "Sommer"}

    # Fault: notification, no write.
    count = len(numbers)
    hass.states.async_set("binary_sensor.heizkurve_fault", "on")
    await hass.async_block_till_done()
    assert len(notify) == 1
    assert "ungültig" in notify[0].data["message"]
    assert len(numbers) == count

    # Switching off: mode back to weather-compensated.
    hass.states.async_set("select.hk_funktion", "Fest")
    hass.states.async_set("switch.heizkurve_active", "off")
    await hass.async_block_till_done()
    assert selects[-1].data == {
        "entity_id": ["select.hk_funktion"],
        "option": "Witterungsgeführt",
    }


async def test_write_blueprint_skips_unchanged_and_unavailable(
    hass: HomeAssistant,
) -> None:
    _heat_pump(hass)
    hass.states.async_set("number.vl_tag", "26.3", {"min": 20, "max": 90})
    hass.states.async_set("number.vl_nacht", "26.3", {"min": 10, "max": 90})
    hass.states.async_set("select.hk_funktion", "Fest")
    numbers = async_mock_service(hass, "number", "set_value")
    selects = async_mock_service(hass, "select", "select_option")
    await _setup(hass, "vorlauf_schreiben.yaml", WRITE_INPUTS)

    # Everything already matches: nothing is written.
    hass.states.async_set("switch.heizkurve_active", "on")
    await hass.async_block_till_done()
    assert numbers == [] and selects == []

    # Setpoint moves by less than 0.3 K: still nothing is written.
    hass.states.async_set("switch.heizkurve_active", "off")
    await hass.async_block_till_done()
    hass.states.async_set("sensor.heizkurve_flow_setpoint", "26.5")
    hass.states.async_set("switch.heizkurve_active", "on")
    await hass.async_block_till_done()
    assert numbers == []

    # A heat pump entity drops out: nothing is written, not even the others.
    hass.states.async_set("switch.heizkurve_active", "off")
    await hass.async_block_till_done()
    selects.clear()
    hass.states.async_set("sensor.heizkurve_flow_setpoint", "27.0")
    hass.states.async_set("number.vl_nacht", "unavailable")
    hass.states.async_set("switch.heizkurve_active", "on")
    await hass.async_block_till_done()
    assert numbers == [] and selects == []

    # Back again: both changed values are written.
    hass.states.async_set("switch.heizkurve_active", "off")
    await hass.async_block_till_done()
    hass.states.async_set("number.vl_nacht", "26.3", {"min": 10, "max": 90})
    hass.states.async_set("switch.heizkurve_active", "on")
    await hass.async_block_till_done()
    assert sorted(c.data["entity_id"][0] for c in numbers) == [
        "number.vl_extra", "number.vl_nacht", "number.vl_tag"
    ]


async def test_write_blueprint_minimal_inputs(hass: HomeAssistant) -> None:
    _heat_pump(hass)
    hass.states.async_set("switch.heizkurve_active", "on")
    numbers = async_mock_service(hass, "number", "set_value")
    selects = async_mock_service(hass, "select", "select_option")
    await _setup(
        hass,
        "vorlauf_schreiben.yaml",
        {key: WRITE_INPUTS[key] for key in ("setpoint", "active_switch", "targets")},
    )
    hass.states.async_set("switch.heizkurve_active", "off")
    await hass.async_block_till_done()
    hass.states.async_set("switch.heizkurve_active", "on")
    await hass.async_block_till_done()
    # Default min_change 0.3 K: vl_tag (0.1 K off) stays, vl_nacht is written.
    assert [c.data["entity_id"][0] for c in numbers] == ["number.vl_nacht"]
    assert selects == []


async def test_lock_blueprint(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.heizkurve_cycling_lock", "off")
    hass.states.async_set("select.raum_thermostat", "Aus")
    selects = async_mock_service(hass, "select", "select_option")
    notify = async_mock_service(hass, "notify", "phone")
    await _setup(
        hass,
        "taktsperre.yaml",
        {
            "lock_sensor": "binary_sensor.heizkurve_cycling_lock",
            "target_select": "select.raum_thermostat",
            "notify_action": "notify.phone",
        },
    )
    hass.states.async_set(
        "binary_sensor.heizkurve_cycling_lock",
        "on",
        {"starts_60min": 3, "ende": "2026-10-12T12:00:00+00:00"},
    )
    await hass.async_block_till_done()
    assert selects[-1].data == {"entity_id": ["select.raum_thermostat"], "option": "An"}
    assert "3 Starts" in notify[0].data["message"]

    hass.states.async_set("select.raum_thermostat", "An")
    hass.states.async_set("binary_sensor.heizkurve_cycling_lock", "off")
    await hass.async_block_till_done()
    assert selects[-1].data == {"entity_id": ["select.raum_thermostat"], "option": "Aus"}
