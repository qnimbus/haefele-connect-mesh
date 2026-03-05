"""Platform for Häfele Connect Mesh light integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from datetime import datetime, UTC

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util.color import (
    value_to_brightness,
    brightness_to_value,
    color_temperature_kelvin_to_mired,
)
from homeassistant.util.percentage import percentage_to_ranged_value

from .const import (
    DOMAIN,
    NAME,
    BRIGHTNESS_SCALE_PERCENTAGE,
    BRIGHTNESS_SCALE_MESH,
    BRIGHTNESS_SCALE_HA,
    MIN_KELVIN,
    MAX_KELVIN,
    MIN_MIREDS,
    MAX_MIREDS,
)
from .coordinator import HafeleUpdateCoordinator
from .mqtt.coordinator import HafeleMQTTCoordinator
from .models.device import Device as HafeleDevice
from .models.mqtt_device import MQTTDevice

_LOGGER = logging.getLogger(__name__)

# Freshness limit for MQTT devices (push-based; 10 minutes)
_MQTT_FRESHNESS_SECONDS = 600
# Freshness limit for cloud devices (polled every 30 s; 2 minutes)
_CLOUD_FRESHNESS_SECONDS = 120


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Häfele Connect Mesh Light platform."""
    runtime_data = config_entry.runtime_data

    lights = [device for device in runtime_data.devices if device.is_light]
    entities = [
        HaefeleConnectMeshLight(runtime_data.coordinators[light.id], light, config_entry)
        for light in lights
    ]

    if entities:
        async_add_entities(entities)


class HaefeleConnectMeshLight(CoordinatorEntity, LightEntity, RestoreEntity):
    """Representation of a Häfele Connect Mesh Light."""

    def __init__(
        self,
        coordinator: HafeleUpdateCoordinator | HafeleMQTTCoordinator,
        device: HafeleDevice | MQTTDevice,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the light."""
        super().__init__(coordinator)

        self._device = device
        self._entry = entry
        self._attr_unique_id = f"{device.id}_light"
        self._attr_name = None
        self._attr_has_entity_name = True

        if device.supports_hsl:
            self._attr_color_mode = ColorMode.HS
            self._attr_supported_color_modes = {ColorMode.HS}
        elif device.supports_color_temp:
            self._attr_color_mode = ColorMode.COLOR_TEMP
            self._attr_supported_color_modes = {ColorMode.COLOR_TEMP}
            self._attr_min_mireds = MIN_MIREDS
            self._attr_max_mireds = MAX_MIREDS
        else:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        _LOGGER.debug(
            "Coordinator update for %s: Raw Data=%s, Is On=%s, Brightness=%s",
            self.entity_id or self._device.name,
            self.coordinator.data,
            self.is_on,
            self.brightness,
        )
        super()._handle_coordinator_update()

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
        sw_version = getattr(self._device, "bootloader_version", None)

        return DeviceInfo(
            identifiers={(DOMAIN, self._device.id)},
            name=self.entity_id or self._device.name,
            manufacturer="Häfele",
            model=model,
            sw_version=sw_version,
            via_device=(DOMAIN, gateway_id) if gateway_id else None,
            suggested_area=getattr(self._device, "location", None) or None,
        )

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not self.coordinator.last_update_success:
            return False

        freshness = (
            _MQTT_FRESHNESS_SECONDS
            if isinstance(self._device, MQTTDevice)
            else _CLOUD_FRESHNESS_SECONDS
        )

        is_available = (
            self.coordinator.data is not None
            and isinstance(self.coordinator.data.get("state"), dict)
            and "power" in self.coordinator.data["state"]
            and "lightness" in self.coordinator.data["state"]
            and (datetime.now(UTC) - self._device.last_updated).total_seconds()
            < freshness
        )

        _LOGGER.debug(
            "Availability check for %s: %s (Data: %s, Last Update: %s)",
            self.entity_id or self._device.name,
            is_available,
            self.coordinator.data,
            self._device.last_updated,
        )
        return is_available

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        if not self.available:
            return None
        _LOGGER.debug(
            "Checking is_on for %s with data: %s", self.entity_id or self._device.name, self.coordinator.data
        )
        return self.coordinator.data["state"]["power"]

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        if not self.available or not self.is_on:
            return None

        lightness = self.coordinator.data["state"].get("lightness")
        if lightness is not None:
            return value_to_brightness(BRIGHTNESS_SCALE_MESH, lightness)
        return None

    @property
    def color_temp(self) -> int | None:
        """Return the color temperature in mireds."""
        if not self.available or not self.is_on or not self._device.supports_color_temp:
            return None

        temperature = self.coordinator.data["state"].get("temperature")
        if temperature is not None:
            kelvin = MIN_KELVIN + (temperature / 65535) * (MAX_KELVIN - MIN_KELVIN)
            return color_temperature_kelvin_to_mired(kelvin)
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        try:
            current = self.coordinator.data["state"]
            new_state = {
                "power": True,
                "lightness": current.get("lightness", 0),
                "lastLightness": current.get("lastLightness", current.get("lightness", 0)),
            }

            if ATTR_BRIGHTNESS in kwargs:
                try:
                    lightness = brightness_to_value(
                        BRIGHTNESS_SCALE_PERCENTAGE, kwargs[ATTR_BRIGHTNESS]
                    )
                except ValueError as ex:
                    raise ServiceValidationError(
                        f"Invalid brightness value for {self.entity_id or self._device.name}: {ex}"
                    ) from ex

                try:
                    await self.coordinator.async_set_lightness(lightness / 100)
                    new_state["lightness"] = percentage_to_ranged_value(
                        BRIGHTNESS_SCALE_MESH, lightness
                    )
                except Exception as ex:
                    raise HomeAssistantError(
                        f"Failed to set brightness for {self.entity_id or self._device.name}: {ex}"
                    ) from ex

            if ATTR_COLOR_TEMP_KELVIN in kwargs and self._device.supports_color_temp:
                kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
                try:
                    await self.coordinator.async_set_temperature(kelvin)
                    new_state["temperature"] = round(
                        ((kelvin - MIN_KELVIN) / (MAX_KELVIN - MIN_KELVIN)) * 65535
                    )
                except ValueError as ex:
                    raise ServiceValidationError(
                        f"Invalid color temperature value for {self.entity_id or self._device.name}: {ex}"
                    ) from ex
                except Exception as ex:
                    raise HomeAssistantError(
                        f"Failed to set color temperature for {self.entity_id or self._device.name}: {ex}"
                    ) from ex

            if ATTR_HS_COLOR in kwargs and self._device.supports_hsl:
                try:
                    hue, saturation = kwargs[ATTR_HS_COLOR]
                    await self.coordinator.async_set_hsl(hue, saturation / 100)
                    new_state["hue"] = hue
                    new_state["saturation"] = saturation
                except ValueError as ex:
                    raise ServiceValidationError(
                        f"Invalid HS color values for {self.entity_id or self._device.name}: {ex}"
                    ) from ex
                except Exception as ex:
                    raise HomeAssistantError(
                        f"Failed to set HS color for {self.entity_id or self._device.name}: {ex}"
                    ) from ex

            try:
                await self.coordinator.async_set_power(True)
            except Exception as ex:
                raise HomeAssistantError(
                    f"Failed to power on {self.entity_id or self._device.name}: {ex}"
                ) from ex

            # Optimistic update — reflects change before next poll/push
            self.coordinator.data = {"state": new_state}
            self.async_write_ha_state()

            if hasattr(self.coordinator, "async_request_state"):
                await asyncio.sleep(1.0)
                await self.coordinator.async_request_state()

        except (ServiceValidationError, HomeAssistantError):
            raise
        except Exception as ex:
            _LOGGER.exception("Unexpected error turning on %s", self.entity_id or self._device.name)
            raise HomeAssistantError(f"Unexpected error turning on {self.entity_id or self._device.name}") from ex

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        try:
            await self.coordinator.async_set_power(False)

            # Optimistic update
            current = self.coordinator.data["state"]
            self.coordinator.data = {
                "state": {
                    "power": False,
                    "lightness": current.get("lightness", 0),
                    "lastLightness": current.get("lastLightness", current.get("lightness", 0)),
                }
            }
            self.async_write_ha_state()

            if hasattr(self.coordinator, "async_request_state"):
                await asyncio.sleep(1.0)
                await self.coordinator.async_request_state()

        except Exception as ex:
            _LOGGER.error("Failed to turn off light %s: %s", self.entity_id or self._device.name, str(ex))

    @property
    def extra_state_attributes(self) -> dict:
        """Return additional state attributes."""
        attrs: dict[str, Any] = {
            "device_id": self._device.id,
        }

        # Cloud-specific attributes
        device_type = getattr(self._device, "type", None)
        if device_type is not None:
            attrs["device_type"] = device_type

        bootloader = getattr(self._device, "bootloader_version", None)
        if bootloader is not None:
            attrs["bootloader_version"] = bootloader

        network_id = getattr(self._device, "network_id", None)
        if network_id is not None:
            attrs["network_id"] = network_id
            entry = self.platform.config_entry
            if entry and entry.data.get("network_id") == network_id:
                attrs["network_name"] = entry.title

        update_interval = self.coordinator.update_interval
        if update_interval is not None:
            attrs["update_interval"] = update_interval.total_seconds()

        return attrs

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        if self.coordinator.data is None:
            if last_state := await self.async_get_last_state():
                if last_state.state == "on":
                    self._attr_is_on = True
                    self._attr_brightness = last_state.attributes.get("brightness", 255)
                else:
                    self._attr_is_on = False
                    self._attr_brightness = 0

    def turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        raise NotImplementedError(
            "Please use the async_turn_on method instead. This entity only supports async operation."
        )

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        raise NotImplementedError(
            "Please use the async_turn_off method instead. This entity only supports async operation."
        )
