"""DataUpdateCoordinator for Häfele Connect Mesh."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api.client import HafeleClient
from .const import (
    CONF_DEVICE_DETAILS_UPDATE_INTERVAL,
    CONF_NEW_DEVICES_CHECK_INTERVAL,
    CONF_SCAN_INTERVAL,
    DEFAULT_DEVICE_DETAILS_UPDATE_INTERVAL,
    DEFAULT_NEW_DEVICES_CHECK_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_KELVIN,
    MIN_KELVIN,
)
from .exceptions import HafeleAPIError
from .models.device import Device

_LOGGER = logging.getLogger(__name__)


class HafeleUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: HafeleClient,
        device: Device,
        entry: ConfigEntry,
    ) -> None:
        """Initialize."""
        self._entry = entry
        self._entry_id = entry.entry_id

        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        super().__init__(
            hass,
            _LOGGER,
            name=f"{device.name}",
            update_interval=timedelta(seconds=scan_interval),
            always_update=False,
        )

        self.client = client
        self.device = device
        self._device_registry = dr.async_get(hass)
        self._last_device_check = datetime.min
        self._last_new_devices_check = datetime.min
        self._device_check_task: asyncio.Task | None = None
        self._new_devices_check_task: asyncio.Task | None = None

    @property
    def device_details_update_interval(self) -> timedelta:
        """Get the device details update interval."""
        minutes = self._entry.options.get(
            CONF_DEVICE_DETAILS_UPDATE_INTERVAL, DEFAULT_DEVICE_DETAILS_UPDATE_INTERVAL
        )
        return timedelta(minutes=minutes)

    @property
    def new_devices_check_interval(self) -> timedelta:
        """Get the new devices check interval."""
        minutes = self._entry.options.get(
            CONF_NEW_DEVICES_CHECK_INTERVAL, DEFAULT_NEW_DEVICES_CHECK_INTERVAL
        )
        return timedelta(minutes=minutes)

    @property
    def _async_add_entities(self):
        """Get the async_add_entities callback."""
        return self.hass.data[DOMAIN][self._entry_id]["async_add_entities"]

    async def _check_device_details(self) -> None:
        """Check for device detail updates in a separate task."""
        try:
            # Use Home Assistant's timeout context manager
            async with self.hass.timeout.async_timeout(30):  # 30 second timeout
                updated_device = await self.client.get_device_details(self.device.id)

                # If device name has changed, update the device registry
                if updated_device.name != self.device.name:
                    _LOGGER.debug(
                        "Device name changed from '%s' to '%s'",
                        self.device.name,
                        updated_device.name,
                    )

                    # Update device registry
                    device_entry = self._device_registry.async_get_device(
                        identifiers={(DOMAIN, self.device.id)}
                    )
                    if device_entry:
                        self._device_registry.async_update_device(
                            device_entry.id, name=updated_device.name
                        )

                    # Update local device reference
                    self.device = updated_device
                    # Update coordinator name
                    self.name = updated_device.name

        except TimeoutError:
            _LOGGER.error("Timeout checking device details for %s", self.device.name)
        except Exception as error:
            _LOGGER.error(
                "Error checking device details for %s: %s", self.device.name, str(error)
            )
        finally:
            self._device_check_task = None

    async def _check_for_new_entities(self) -> None:
        """Check for new entities exposed by the API."""
        try:
            async with self.hass.timeout.async_timeout(60):
                try:
                    # Get current devices from API with specific timeout
                    new_devices = await asyncio.wait_for(
                        self.client.get_devices_for_network(self.device.network_id),
                        timeout=30,
                    )
                except TimeoutError:
                    _LOGGER.warning(
                        "Timeout getting devices for network %s, will retry later",
                        self.device.network_id,
                    )
                    return

                # Get existing device IDs
                existing_device_ids = {
                    device.id for device in self._entry.runtime_data.devices
                }

                # Find new devices
                new_device_objects = [
                    device
                    for device in new_devices
                    if device.id not in existing_device_ids
                ]

                if new_device_objects:
                    # Group entities by platform
                    platform_entities = {
                        "light": [],
                        "switch": [],
                        "binary_sensor": [],
                        "sensor": [],
                    }

                    entity_registry = er.async_get(self.hass)
                    for device in new_device_objects:
                        if device.id not in self._entry.runtime_data.coordinators:
                            continue

                        device_id = f"{DOMAIN}_{device.id}"
                        existing_entities = [
                            entry
                            for entry in entity_registry.entities.values()
                            if entry.device_id == device_id
                        ]
                        existing_unique_ids = {
                            entry.unique_id for entry in existing_entities
                        }

                        # Create entities and add them to appropriate platform lists
                        if device.is_light:
                            from .light import HaefeleConnectMeshLight

                            light_unique_id = f"{device.id}_light"
                            if light_unique_id not in existing_unique_ids:
                                platform_entities["light"].append(
                                    HaefeleConnectMeshLight(
                                        self._entry.runtime_data.coordinators[
                                            device.id
                                        ],
                                        device,
                                        self._entry,
                                    )
                                )

                        if device.is_socket:
                            from .switch import HaefeleConnectMeshSwitch

                            switch_unique_id = f"{device.id}_switch"
                            if switch_unique_id not in existing_unique_ids:
                                platform_entities["switch"].append(
                                    HaefeleConnectMeshSwitch(
                                        self._entry.runtime_data.coordinators[
                                            device.id
                                        ],
                                        device,
                                        self._entry,
                                    )
                                )

                        # Add diagnostic entities
                        from .binary_sensor import HaefeleUpdateSuccessSensor
                        from .sensor import HaefeleLastUpdateSensor

                        update_sensor_id = f"{device.id}_last_update_success"
                        if update_sensor_id not in existing_unique_ids:
                            platform_entities["binary_sensor"].append(
                                HaefeleUpdateSuccessSensor(
                                    self._entry.runtime_data.coordinators[device.id],
                                    device,
                                    self._entry,
                                )
                            )

                        last_update_id = f"{device.id}_last_update"
                        if last_update_id not in existing_unique_ids:
                            platform_entities["sensor"].append(
                                HaefeleLastUpdateSensor(
                                    self._entry.runtime_data.coordinators[device.id],
                                    device,
                                    self._entry,
                                )
                            )

                    # Add entities per platform
                    for platform, entities in platform_entities.items():
                        if entities:
                            try:
                                async_add_entities = self.hass.data[DOMAIN][
                                    self._entry_id
                                ].get(f"async_add_{platform}_entities")
                                if async_add_entities:
                                    await asyncio.wait_for(
                                        async_add_entities(entities), timeout=30
                                    )
                            except TimeoutError:
                                _LOGGER.warning(
                                    "Timeout adding %s entities for network %s",
                                    platform,
                                    self.device.network_id,
                                )
                            except Exception as err:
                                _LOGGER.error(
                                    "Error adding %s entities: %s", platform, str(err)
                                )

        except TimeoutError:
            _LOGGER.error(
                "Overall timeout checking for new devices for network %s",
                self.device.network_id,
            )
        except Exception as error:
            _LOGGER.error(
                "Error checking for new devices for network %s: %s",
                self.device.network_id,
                str(error),
            )
        finally:
            self._new_devices_check_task = None

    async def _async_setup(self) -> None:
        """Perform one-time setup tasks."""

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via library."""
        try:
            _LOGGER.debug(
                "Fetching status for device %s (ID: %s)",
                self.device.name,
                self.device.id,
            )
            status = await self.client.get_device_status(self.device.id)

            # Transform status data based on device type
            transformed_data = {"state": {}}

            # Get the power state for all device types
            if "power" in status["state"]:
                transformed_data["state"]["power"] = status["state"]["power"]

            # Add lightness only for light devices
            if self.device.is_light and "lightness" in status["state"]:
                transformed_data["state"]["lightness"] = status["state"]["lightness"]
                transformed_data["state"]["lastLightness"] = status["state"].get(
                    "lastLightness", 0
                )

            # Check if it's time to update device details
            now = datetime.now()
            if (
                now - self._last_device_check > self.device_details_update_interval
                and self._device_check_task is None
            ):
                self._last_device_check = now
                self._device_check_task = self.hass.async_create_task(
                    self._check_device_details()
                )

            # Check if it's time to check for new devices
            if (
                now - self._last_new_devices_check > self.new_devices_check_interval
                and self._new_devices_check_task is None
            ):
                self._last_new_devices_check = now
                self._new_devices_check_task = self.hass.async_create_task(
                    self._check_for_new_entities()
                )

            self.device.update_timestamp()

            _LOGGER.debug(
                "Processed status for device %s: %s", self.device.name, transformed_data
            )
            return transformed_data

        except HafeleAPIError as error:
            self.device.update_timestamp()
            if "401" in str(error):
                # Trigger reauth flow
                _LOGGER.debug("Authentication failed, triggering reauth flow")
                self.hass.async_create_task(
                    self.hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={
                            "source": "reauth",
                            "entry_id": self._entry.entry_id,
                        },
                        data=self._entry.data,
                    )
                )
                raise UpdateFailed("Authentication failed, please reauthenticate")
            raise UpdateFailed(f"Error communicating with API: {error}")
        except asyncio.CancelledError:
            # Re-raise cancelled errors
            raise
        except Exception as error:
            self.device.update_timestamp()
            _LOGGER.exception(
                "Unexpected error fetching %s data: %s", self.device.name, str(error)
            )
            raise UpdateFailed(f"Unexpected error: {error}")

    # ------------------------------------------------------------------
    # Command methods — uniform interface shared with HafeleMQTTCoordinator
    # ------------------------------------------------------------------

    async def async_set_power(self, on: bool) -> None:
        """Turn the device on or off via the cloud API."""
        if on:
            await self.client.power_on(self.device)
        else:
            await self.client.power_off(self.device)

    async def async_set_lightness(self, value: float) -> None:
        """Set brightness (0.0–1.0) via the cloud API."""
        await self.client.set_lightness(self.device, value)

    async def async_set_temperature(self, kelvin: int) -> None:
        """Set color temperature (Kelvin) via the cloud API."""
        mesh_temp = round(((kelvin - MIN_KELVIN) / (MAX_KELVIN - MIN_KELVIN)) * 65535)
        await self.client.set_temperature(self.device, mesh_temp)

    async def async_set_hsl(self, hue: float, saturation: float) -> None:
        """Set HSL color via the cloud API."""
        await self.client.set_hsl(self.device, hue, saturation)
