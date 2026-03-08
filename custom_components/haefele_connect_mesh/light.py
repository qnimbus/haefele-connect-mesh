"""Platform for Häfele Connect Mesh light integration."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.color import (
    brightness_to_value,
    value_to_brightness,
)
from homeassistant.util.percentage import percentage_to_ranged_value

from . import MQTTGroup
from .const import (
    BRIGHTNESS_SCALE_MESH,
    BRIGHTNESS_SCALE_PERCENTAGE,
    DOMAIN,
    MAX_KELVIN,
    MIN_KELVIN,
)
from .coordinator import HafeleUpdateCoordinator
from .models.device import Device as HafeleDevice
from .models.mqtt_device import MQTTDevice
from .mqtt.coordinator import HafeleMQTTCoordinator

_LOGGER = logging.getLogger(__name__)

# Freshness limit for cloud devices (polled every 30 s; 2 minutes)
_CLOUD_FRESHNESS_SECONDS = 120
# Delay before querying actual brightness after a turn-on command with no
# explicit brightness (device was off so lightness=0 at command time).
_BRIGHTNESS_FETCH_DELAY = 0.5


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Häfele Connect Mesh Light platform."""
    runtime_data = config_entry.runtime_data

    lights = [device for device in runtime_data.devices if device.is_light]
    entities: list = [
        HaefeleConnectMeshLight(
            runtime_data.coordinators[light.id], light, config_entry
        )
        for light in lights
    ]

    # Group light entities (MQTT only)
    for group in getattr(runtime_data, "mqtt_groups", []):
        member_coordinators = [
            runtime_data.coordinators[str(addr)]
            for addr in group.device_addrs
            if str(addr) in runtime_data.coordinators
        ]
        if member_coordinators:
            entities.append(
                HafeleMQTTGroupLight(
                    group,
                    member_coordinators,
                    runtime_data.prefix,
                    runtime_data.direct_client,
                    config_entry,
                )
            )

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
            self._attr_min_color_temp_kelvin = MIN_KELVIN
            self._attr_max_color_temp_kelvin = MAX_KELVIN
        else:
            self._attr_color_mode = ColorMode.BRIGHTNESS
            self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        state = (self.coordinator.data or {}).get("state", {})
        _LOGGER.debug(
            "State update for %s: power=%s lightness=%s",
            self.entity_id or self._device.name,
            state.get("power"),
            state.get("lightness"),
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

        state = (self.coordinator.data or {}).get("state")
        if not isinstance(state, dict):
            return False

        has_data = "power" in state and "lightness" in state

        if isinstance(self._device, MQTTDevice):
            # Push-based: no staleness check — a stable light that hasn't changed
            # in a long time should not be reported as unavailable.
            is_available = has_data
        else:
            is_available = (
                has_data
                and (datetime.now(UTC) - self._device.last_updated).total_seconds()
                < _CLOUD_FRESHNESS_SECONDS
            )

        return is_available

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        if not self.available:
            return None
        return self.coordinator.data["state"]["power"]

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        if not self.available or not self.is_on:
            return None

        state = self.coordinator.data["state"]
        # Fall back to lastLightness when lightness is 0 — the gateway reports
        # lightness: 0 while a device is off, so lastLightness preserves the
        # value from the previous on-cycle across off periods and HA restarts.
        lightness = state.get("lightness") or state.get("lastLightness")
        if lightness:
            return value_to_brightness(BRIGHTNESS_SCALE_MESH, lightness)
        return None

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return the color temperature in Kelvin."""
        if not self.available or not self.is_on or not self._device.supports_color_temp:
            return None

        temperature = self.coordinator.data["state"].get("temperature")
        if temperature is not None:
            return round(MIN_KELVIN + (temperature / 65535) * (MAX_KELVIN - MIN_KELVIN))
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        try:
            current = self.coordinator.data["state"]
            new_state = {
                "power": True,
                "lightness": current.get("lightness", 0),
                "lastLightness": current.get(
                    "lastLightness", current.get("lightness", 0)
                ),
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

            # When no brightness was specified and lightness is still 0 (device
            # was off at HA startup so lightnessGet returned 0.0), schedule a
            # delayed state fetch to learn the actual hardware brightness.
            # Only applies to push-based coordinators (cloud self-corrects via poll).
            if (
                ATTR_BRIGHTNESS not in kwargs
                and new_state.get("lightness", 0) == 0
                and hasattr(self.coordinator, "async_request_state")
            ):

                async def _fetch_brightness() -> None:
                    await asyncio.sleep(_BRIGHTNESS_FETCH_DELAY)
                    await self.coordinator.async_request_state()

                self.hass.async_create_task(_fetch_brightness())

        except (ServiceValidationError, HomeAssistantError):
            raise
        except Exception as ex:
            _LOGGER.exception(
                "Unexpected error turning on %s", self.entity_id or self._device.name
            )
            raise HomeAssistantError(
                f"Unexpected error turning on {self.entity_id or self._device.name}"
            ) from ex

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
                    "lastLightness": current.get(
                        "lastLightness", current.get("lightness", 0)
                    ),
                }
            }
            self.async_write_ha_state()

        except Exception as ex:
            _LOGGER.error(
                "Failed to turn off light %s: %s",
                self.entity_id or self._device.name,
                str(ex),
            )

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


class HafeleMQTTGroupLight(LightEntity, RestoreEntity):
    """
    A light entity representing a Häfele BLE Mesh group.

    Commands are published to the group topic so all members respond
    simultaneously. State is aggregated from the individual member coordinators
    which are updated via rawMessage push and/or status topic subscriptions.
    """

    def __init__(
        self,
        group: MQTTGroup,
        member_coordinators: list[HafeleMQTTCoordinator],
        prefix: str,
        direct_client: object | None,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the group light."""
        self._group = group
        self._coordinators = member_coordinators
        self._prefix = prefix
        self._direct_client = direct_client
        self._entry = entry
        self._attr_unique_id = f"group_{group.group_main_addr}"
        self._attr_has_entity_name = True
        self._attr_name = None  # name comes from device_info
        self._attr_color_mode = ColorMode.BRIGHTNESS
        self._attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    async def async_added_to_hass(self) -> None:
        """Subscribe to all member coordinators."""
        await super().async_added_to_hass()
        for coordinator in self._coordinators:
            self.async_on_remove(
                coordinator.async_add_listener(self._handle_member_update)
            )

    @callback
    def _handle_member_update(self) -> None:
        """Called when any member coordinator has new data."""
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        """Register this group as its own HA device."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"group_{self._group.group_main_addr}")},
            name=self._group.group_name,
            manufacturer="Häfele",
            model="Light Group",
        )

    @property
    def available(self) -> bool:
        """Available if at least one member coordinator is healthy."""
        return any(c.last_update_success for c in self._coordinators)

    @property
    def is_on(self) -> bool | None:
        """On if any member is on."""
        if not self.available:
            return None
        return any(
            (c.data or {}).get("state", {}).get("power", False)
            for c in self._coordinators
        )

    @property
    def brightness(self) -> int | None:
        """Average brightness of on-members, in HA scale (0–255)."""
        if not self.is_on:
            return None
        on_lightness = []
        for c in self._coordinators:
            state = (c.data or {}).get("state", {})
            if not state.get("power"):
                continue
            # Prefer actual lightness; fall back to lastLightness if lightness is 0
            # (happens when OnOff rawMessage arrives before a Lightness update)
            lightness = state.get("lightness") or state.get("lastLightness")
            if lightness:
                on_lightness.append(lightness)
        if not on_lightness:
            return None
        avg = round(sum(on_lightness) / len(on_lightness))
        return value_to_brightness(BRIGHTNESS_SCALE_MESH, avg)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the group (and optionally set brightness)."""
        try:
            new_state: dict = {"power": True}
            if ATTR_BRIGHTNESS in kwargs:
                lightness = brightness_to_value(
                    BRIGHTNESS_SCALE_PERCENTAGE, kwargs[ATTR_BRIGHTNESS]
                )
                lightness_frac = lightness / 100
                await self._publish("lightness", lightness_frac)
                new_state["lightness"] = round(lightness_frac * 65535)
            await self._publish("power", True)
            _LOGGER.debug("Group '%s' turn_on published", self._group.group_name)
            fetch_needed = []
            for coordinator in self._coordinators:
                current = (coordinator.data or {}).get("state", {})
                coordinator.async_set_updated_data({"state": {**current, **new_state}})
                if ATTR_BRIGHTNESS not in kwargs and current.get("lightness", 0) == 0:
                    fetch_needed.append(coordinator)
            if fetch_needed:

                async def _fetch_group_brightness() -> None:
                    await asyncio.sleep(_BRIGHTNESS_FETCH_DELAY)
                    for coord in fetch_needed:
                        await coord.async_request_state()
                        await asyncio.sleep(0.1)

                self.hass.async_create_task(_fetch_group_brightness())
        except Exception:
            _LOGGER.exception("Failed to turn on group '%s'", self._group.group_name)
            raise HomeAssistantError(
                f"Failed to turn on group {self._group.group_name}"
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the group."""
        try:
            await self._publish("power", False)
            _LOGGER.debug("Group '%s' turn_off published", self._group.group_name)
            for coordinator in self._coordinators:
                current = (coordinator.data or {}).get("state", {})
                coordinator.async_set_updated_data(
                    {"state": {**current, "power": False}}
                )
        except Exception:
            _LOGGER.exception("Failed to turn off group '%s'", self._group.group_name)
            raise HomeAssistantError(
                f"Failed to turn off group {self._group.group_name}"
            )

    async def _publish(self, command: str, payload: Any) -> None:
        """Publish a command to the group topic."""
        import homeassistant.components.mqtt as ha_mqtt  # noqa: PLC0415

        topic = f"{self._prefix}/groups/{self._group.group_name}/{command}"
        if isinstance(payload, bool) or isinstance(payload, (dict, list)):
            payload_str = json.dumps(payload)
        else:
            payload_str = str(payload)
        if self._direct_client:
            await self._direct_client.async_publish(topic, payload_str)
        else:
            await ha_mqtt.async_publish(self.hass, topic, payload_str)
