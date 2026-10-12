"""Config and options flow for the Heizkurve integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ABS_MAX_FLOW,
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
    DEFAULT_ABS_MAX_FLOW,
    DEFAULT_ABS_MIN_FLOW,
    DEFAULT_MODE_DHW,
    DOMAIN,
)

SOURCE_KEYS = (
    CONF_OUTDOOR,
    CONF_OUTDOOR_FALLBACK,
    CONF_ROOM,
    CONF_TARGET,
    CONF_WEATHER,
    CONF_PV_FORECAST,
    CONF_ABS_MIN_FLOW,
    CONF_ABS_MAX_FLOW,
    CONF_COMPRESSOR,
    CONF_MODE,
    CONF_MODE_DHW,
    CONF_HEAT_METER,
    CONF_COMPARISON,
)

TEMP_SENSOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
)


def _basis_schema(with_name: bool) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if with_name:
        fields[vol.Required(CONF_NAME, default="Heizkurve")] = selector.TextSelector()
    fields.update(
        {
            vol.Required(CONF_OUTDOOR): TEMP_SENSOR,
            vol.Optional(CONF_OUTDOOR_FALLBACK): TEMP_SENSOR,
            vol.Optional(CONF_ROOM): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class="temperature", multiple=True
                )
            ),
            vol.Optional(CONF_TARGET): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=["input_number", "number", "sensor"]
                )
            ),
        }
    )
    return vol.Schema(fields)


FORECAST_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_WEATHER): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="weather", multiple=True)
        ),
        vol.Optional(CONF_PV_FORECAST): selector.EntitySelector(
            selector.EntitySelectorConfig(
                domain="sensor", integration="helios_forecast"
            )
        ),
    }
)

FLOW_LIMIT = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=10, max=70, step=0.5, unit_of_measurement="°C",
        mode=selector.NumberSelectorMode.BOX,
    )
)

PLANT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_ABS_MIN_FLOW, default=DEFAULT_ABS_MIN_FLOW): FLOW_LIMIT,
        vol.Required(CONF_ABS_MAX_FLOW, default=DEFAULT_ABS_MAX_FLOW): FLOW_LIMIT,
        vol.Optional(CONF_COMPRESSOR): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="binary_sensor")
        ),
        vol.Optional(CONF_MODE): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["sensor", "select"])
        ),
        vol.Optional(CONF_MODE_DHW, default=DEFAULT_MODE_DHW): selector.TextSelector(),
        vol.Optional(CONF_HEAT_METER): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="energy")
        ),
        vol.Optional(CONF_COMPARISON): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor")
        ),
    }
)


def _check_limits(user_input: dict[str, Any]) -> dict[str, str]:
    if user_input[CONF_ABS_MIN_FLOW] >= user_input[CONF_ABS_MAX_FLOW]:
        return {"base": "flow_limits"}
    return {}


class HeizkurveConfigFlow(ConfigFlow, domain=DOMAIN):
    """Three steps: basis, forecast, plant."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_forecast()
        return self.async_show_form(step_id="user", data_schema=_basis_schema(True))

    async def async_step_forecast(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_plant()
        return self.async_show_form(step_id="forecast", data_schema=FORECAST_SCHEMA)

    async def async_step_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check_limits(user_input)
            if not errors:
                self._data.update(user_input)
                name = self._data.pop(CONF_NAME)
                return self.async_create_entry(title=name, data=self._data)
        return self.async_show_form(
            step_id="plant", data_schema=PLANT_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HeizkurveOptionsFlow:
        return HeizkurveOptionsFlow()


class HeizkurveOptionsFlow(OptionsFlowWithReload):
    """Change the sources later, in the same three steps."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    def _form(self, step_id: str, schema: vol.Schema, errors=None):
        return self.async_show_form(
            step_id=step_id,
            data_schema=self.add_suggested_values_to_schema(schema, self._current),
            errors=errors or {},
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_forecast()
        return self._form("init", _basis_schema(False))

    async def async_step_forecast(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_plant()
        return self._form("forecast", FORECAST_SCHEMA)

    async def async_step_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _check_limits(user_input)
            if not errors:
                self._data.update(user_input)
                # A cleared optional field is missing from the input: store it
                # as None so it overrides the value from the initial setup.
                options = {key: self._data.get(key) for key in SOURCE_KEYS}
                return self.async_create_entry(data=options)
        return self._form("plant", PLANT_SCHEMA, errors)
