"""The Häfele Connect Mesh integration."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryNotReady
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr

from .api.client import HafeleClient
from .coordinator import HafeleUpdateCoordinator
from .exceptions import HafeleAPIError
from .mqtt.coordinator import HafeleMQTTCoordinator
from .mqtt.direct_client import DirectMQTTClient
from .models.mqtt_device import MQTTDevice
from .const import (
    DOMAIN,
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_CLOUD,
    CONNECTION_TYPE_MQTT,
    CONF_MQTT_TOPIC_PREFIX,
    DEFAULT_MQTT_TOPIC_PREFIX,
    CONF_MQTT_USE_HA,
    CONF_MQTT_BROKER,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    CONF_MQTT_PASSWORD,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    CONF_POLLING_ENABLED,
    DEFAULT_POLLING_ENABLED,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]

PARALLEL_UPDATES = 0


@dataclass
class HafeleEntryData:
    """Runtime data for a Häfele Connect Mesh config entry."""

    coordinators: dict = field(default_factory=dict)
    devices: list = field(default_factory=list)
    gateways: list = field(default_factory=list)
    client: object | None = None
    network_id: str | None = None
    prefix: str | None = None
    direct_client: object | None = None


type HafeleConfigEntry = ConfigEntry[HafeleEntryData]

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

# Timeout (seconds) to wait for device discovery via MQTT
_MQTT_DISCOVERY_TIMEOUT = 10


async def _rotational_poll_loop(
    hass: HomeAssistant,
    coordinators: dict,
    poll_interval: int,
) -> None:
    """Poll each MQTT device in rotation, spacing polls evenly within poll_interval."""
    try:
        # Immediate burst on startup so all devices become available right away.
        for coordinator in list(coordinators.values()):
            hass.async_create_task(coordinator.async_request_state())

        while True:
            snapshot = list(coordinators.values())
            num = len(snapshot)
            if num == 0:
                await asyncio.sleep(poll_interval)
                continue
            sleep_between = max(2.0, poll_interval / num)
            for coordinator in snapshot:
                # Fire-and-forget: do not await so the loop never blocks the event loop.
                hass.async_create_task(coordinator.async_request_state())
                await asyncio.sleep(sleep_between)
    except asyncio.CancelledError:
        pass


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Häfele Connect Mesh component."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Häfele Connect Mesh from a config entry."""
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    connection_type = entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_CLOUD)

    if connection_type == CONNECTION_TYPE_MQTT:
        return await _async_setup_mqtt(hass, entry)

    return await _async_setup_cloud(hass, entry)


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


# ---------------------------------------------------------------------------
# Cloud setup
# ---------------------------------------------------------------------------

async def _async_setup_cloud(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration using the Häfele cloud API."""
    try:
        session = async_get_clientsession(hass)
        client = HafeleClient(entry.data["api_token"], session, timeout=30)
        network_id = entry.data["network_id"]

        device_registry = dr.async_get(hass)
        try:
            async with asyncio.timeout(30):
                gateways = await client.get_gateways()
                network_gateways = [g for g in gateways if g.network_id == network_id]

                for gateway in network_gateways:
                    device_registry.async_get_or_create(
                        config_entry_id=entry.entry_id,
                        identifiers={(DOMAIN, gateway.id)},
                        name=f"Häfele Gateway {gateway.id[:8]}",
                        manufacturer="Häfele",
                        model="Connect Mesh Gateway",
                        sw_version=gateway.firmware,
                        entry_type=dr.DeviceEntryType.SERVICE,
                    )
        except HafeleAPIError as err:
            if "401" in str(err):
                _LOGGER.debug("Authentication failed, triggering reauth flow")
                hass.async_create_task(
                    hass.config_entries.flow.async_init(
                        DOMAIN,
                        context={"source": "reauth", "entry_id": entry.entry_id},
                        data=entry.data,
                    )
                )
                return False
            raise ConfigEntryNotReady("Failed getting gateways") from err

        entry.runtime_data = HafeleEntryData(
            client=client,
            gateways=network_gateways,
            coordinators={},
            network_id=network_id,
            devices=[],
        )

        try:
            async with asyncio.timeout(30):
                devices = await client.get_devices_for_network(network_id)
        except asyncio.TimeoutError as err:
            raise ConfigEntryNotReady("Timeout getting devices") from err

        for device in devices:
            try:
                _LOGGER.debug(
                    "Initializing coordinator for device %s (type: %s)",
                    device.id,
                    device.type
                )
                timeout = 30 if getattr(device, "is_socket", False) else 15
                coordinator = HafeleUpdateCoordinator(hass, client, device, entry)
                async with asyncio.timeout(timeout):
                    await coordinator.async_config_entry_first_refresh()
                entry.runtime_data.coordinators[device.id] = coordinator
                entry.runtime_data.devices.append(device)
            except asyncio.TimeoutError:
                _LOGGER.warning(
                    "Timeout initializing coordinator for device %s (type: %s), skipping",
                    device.id,
                    device.type
                )
                continue
            except Exception as err:
                _LOGGER.error(
                    "Error initializing coordinator for device %s: %s",
                    device.id,
                    str(err)
                )
                continue

        if not entry.runtime_data.coordinators:
            raise ConfigEntryNotReady("No devices could be initialized, will retry later")

        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        return True

    except HafeleAPIError as error:
        if "401" in str(error):
            _LOGGER.debug("Authentication failed, triggering reauth flow")
            hass.async_create_task(
                hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": "reauth", "entry_id": entry.entry_id},
                    data=entry.data,
                )
            )
            return False
        _LOGGER.error("Failed to set up Häfele Connect Mesh (cloud): %s", str(error))
        raise ConfigEntryNotReady(str(error)) from error
    except Exception as error:
        _LOGGER.error("Failed to set up Häfele Connect Mesh (cloud): %s", str(error))
        raise ConfigEntryNotReady from error


# ---------------------------------------------------------------------------
# MQTT setup
# ---------------------------------------------------------------------------

async def _async_setup_mqtt(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the integration using a local MQTT broker."""
    import homeassistant.components.mqtt as ha_mqtt  # noqa: PLC0415 - avoids subpackage shadowing

    use_ha = entry.data.get(CONF_MQTT_USE_HA, True)
    direct_client: DirectMQTTClient | None = None

    if use_ha:
        try:
            connected = ha_mqtt.is_connected(hass)
        except KeyError:
            raise ConfigEntryNotReady(
                "HA MQTT integration is not configured. "
                "Add the MQTT integration in Home Assistant first, or switch to direct broker mode."
            )
        if not connected:
            raise ConfigEntryNotReady("HA MQTT client is not connected")
    else:
        broker = entry.data[CONF_MQTT_BROKER]
        port = int(entry.data.get(CONF_MQTT_PORT, 1883))
        username = entry.data.get(CONF_MQTT_USERNAME) or None
        password = entry.data.get(CONF_MQTT_PASSWORD) or None

        direct_client = DirectMQTTClient(broker, port, username, password)
        try:
            await direct_client.async_connect()
        except ConnectionError as err:
            raise ConfigEntryNotReady(str(err)) from err

    prefix = entry.data.get(CONF_MQTT_TOPIC_PREFIX, DEFAULT_MQTT_TOPIC_PREFIX)
    polling_enabled = bool(
        entry.options.get(CONF_POLLING_ENABLED, entry.data.get(CONF_POLLING_ENABLED, DEFAULT_POLLING_ENABLED))
    )
    poll_interval = int(
        entry.options.get(CONF_POLL_INTERVAL, entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL))
    )
    discovery_topic = f"{prefix}/lights"

    # Collect discovered devices from the discovery topic
    discovered_devices: list[MQTTDevice] = []
    discovery_event = asyncio.Event()

    @callback
    def _on_discovery(msg) -> None:
        """Handle a discovery message listing all lights."""
        try:
            payload = json.loads(msg.payload)
        except (json.JSONDecodeError, TypeError):
            _LOGGER.warning("Invalid MQTT discovery payload: %s", msg.payload)
            discovery_event.set()
            return

        _LOGGER.debug("MQTT discovery payload on %s: %s", msg.topic, payload)

        if isinstance(payload, list):
            for item in payload:
                try:
                    device = MQTTDevice(
                        device_name=item["device_name"],
                        device_addr=item["device_addr"],
                        device_types=item.get("device_types", ["light"]),
                    )
                    discovered_devices.append(device)
                    _LOGGER.debug(
                        "Discovered device: %s (addr=%s, types=%s)",
                        device.device_name,
                        device.device_addr,
                        device.device_types,
                    )
                except (KeyError, TypeError) as err:
                    _LOGGER.warning("Skipping malformed device entry: %s", err)
        elif isinstance(payload, dict):
            # Single-device payload
            try:
                device = MQTTDevice(
                    device_name=payload["device_name"],
                    device_addr=payload["device_addr"],
                    device_types=payload.get("device_types", ["light"]),
                )
                discovered_devices.append(device)
                _LOGGER.debug(
                    "Discovered device: %s (addr=%s, types=%s)",
                    device.device_name,
                    device.device_addr,
                    device.device_types,
                )
            except (KeyError, TypeError) as err:
                _LOGGER.warning("Skipping malformed device entry: %s", err)

        discovery_event.set()

    if direct_client:
        unsubscribe_discovery = await direct_client.async_subscribe(
            discovery_topic, _on_discovery
        )
    else:
        unsubscribe_discovery = await ha_mqtt.async_subscribe(
            hass, discovery_topic, _on_discovery, qos=0
        )

    # Wait for the gateway to respond with device list
    try:
        await asyncio.wait_for(
            discovery_event.wait(), timeout=_MQTT_DISCOVERY_TIMEOUT
        )
    except asyncio.TimeoutError:
        _LOGGER.warning(
            "MQTT device discovery timed out after %ds on topic '%s'. "
            "Proceeding with %d device(s) found so far.",
            _MQTT_DISCOVERY_TIMEOUT,
            discovery_topic,
            len(discovered_devices),
        )
    finally:
        unsubscribe_discovery()

    # Filter to controllable light devices only; Switch-type nodes (physical
    # switches, remotes, sensors) are input-only and need no HA entity.
    light_devices = [d for d in discovered_devices if d.is_light]
    if len(light_devices) < len(discovered_devices):
        skipped = [d.device_name for d in discovered_devices if not d.is_light]
        _LOGGER.debug("Skipping non-light devices: %s", skipped)

    # Build coordinators for each discovered light device
    coordinators: dict[str, HafeleMQTTCoordinator] = {}
    for device in light_devices:
        coordinator = HafeleMQTTCoordinator(hass, device, prefix, direct_client=direct_client)
        await coordinator.async_setup()
        coordinators[device.id] = coordinator

    entry.runtime_data = HafeleEntryData(
        coordinators=coordinators,
        devices=light_devices,
        gateways=[],
        prefix=prefix,
        direct_client=direct_client,
    )

    if polling_enabled and coordinators:
        poll_task = hass.async_create_background_task(
            _rotational_poll_loop(hass, coordinators, poll_interval),
            name="hafele_mqtt_rotational_poll",
        )
        async def _cancel_poll_task() -> None:
            poll_task.cancel()

        entry.async_on_unload(_cancel_poll_task)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info(
        "Häfele Connect Mesh (MQTT) set up with %d light device(s) (%d total discovered)",
        len(light_devices),
        len(discovered_devices),
    )
    return True


# ---------------------------------------------------------------------------
# Unload
# ---------------------------------------------------------------------------

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    entry_data: HafeleEntryData = entry.runtime_data

    # Cancel MQTT subscriptions / shut down cloud coordinators before unloading platforms
    for coordinator in entry_data.coordinators.values():
        if isinstance(coordinator, HafeleMQTTCoordinator):
            await coordinator.async_unsubscribe()
        else:
            coordinator.async_shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Disconnect the direct MQTT client if one was created
        if entry_data.direct_client:
            await entry_data.direct_client.async_disconnect()

    return unload_ok
