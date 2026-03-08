"""Platform for Häfele Connect Mesh sensor integration."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import HafeleUpdateCoordinator
from .models.device import Device

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Häfele Connect Mesh Sensor platform."""
    runtime_data = config_entry.runtime_data

    entities = [
        HaefeleLastUpdateSensor(
            runtime_data.coordinators[device.id], device, config_entry
        )
        for device in runtime_data.devices
    ]

    if entities:
        async_add_entities(entities)


class HaefeleLastUpdateSensor(CoordinatorEntity, SensorEntity):
    """Sensor for tracking last update time of Häfele devices."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_update"
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: HafeleUpdateCoordinator,
        device: Device,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)

        self._device = device
        self._entry = entry
        self._attr_unique_id = f"{device.id}_last_update"
        self._attr_has_entity_name = True
        self._attr_translation_key = "last_update"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info."""
        gateway_id = None
        gateways = self._entry.runtime_data.gateways
        if gateways:
            gateway_id = gateways[0].id

        device_type = getattr(self._device, "type", None)
        model = (
            device_type.value.split(".")[-1].capitalize()
            if device_type is not None
            else "Light"
        )

        return DeviceInfo(
            identifiers={(DOMAIN, self._device.id)},
            name=self._device.name,
            manufacturer="Häfele",
            model=model,
            sw_version=getattr(self._device, "bootloader_version", None),
            via_device=(DOMAIN, gateway_id) if gateway_id else None,
            suggested_area=getattr(self._device, "location", None) or None,
        )

    @property
    def native_value(self) -> datetime:
        """Return the last update timestamp."""
        return self._device.last_updated
