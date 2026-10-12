"""Button of the Heizkurve integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_ROOM
from .coordinator import HeizkurveConfigEntry, HeizkurveCoordinator
from .entity import HeizkurveEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HeizkurveConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the I-term reset button (only with room temperature)."""
    coordinator = entry.runtime_data
    if coordinator.has(CONF_ROOM):
        async_add_entities([ResetIntegralButton(coordinator)])


class ResetIntegralButton(HeizkurveEntity, ButtonEntity):
    """Sets the I-term back to 0."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:restore"

    def __init__(self, coordinator: HeizkurveCoordinator) -> None:
        super().__init__(coordinator, "reset_integral")

    async def async_press(self) -> None:
        await self.coordinator.async_reset_integral()
