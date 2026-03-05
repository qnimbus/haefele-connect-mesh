"""Platform for Häfele Connect Mesh binary sensor integration."""

from __future__ import annotations

import logging

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import EntityCategory

from .const import DOMAIN
from .coordinator import HafeleUpdateCoordinator
from .models.device import Device

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Häfele Connect Mesh Binary Sensor platform."""
    runtime_data = config_entry.runtime_data

    entities = [
        HaefeleUpdateSuccessSensor(runtime_data.coordinators[device.id], device, config_entry)
        for device in runtime_data.devices
    ]

    if entities:
        async_add_entities(entities)


class HaefeleUpdateSuccessSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for tracking update success of Häfele devices."""

    def __init__(
        self,
        coordinator: HafeleUpdateCoordinator,
        device: Device,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)

        self._device = device
        self._entry = entry
        self._attr_translation_key = "last_update_success"
        self._attr_unique_id = f"{device.id}_last_update_success"
        self._attr_has_entity_name = True
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
        self._attr_entity_registry_enabled_default = False
        self._attr_entity_category = EntityCategory.DIAGNOSTIC

    async def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        return super()._handle_coordinator_update()

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
        )

    @property
    def is_on(self) -> bool:
        """Return True if the last update was successful."""
        return self.coordinator.last_update_success

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Always return True since this entity reflects the update status itself
        return True
