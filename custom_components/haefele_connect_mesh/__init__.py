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
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr

from .api.client import HafeleClient
from .coordinator import HafeleUpdateCoordinator
from .exceptions import HafeleAPIError
from .mqtt.coordinator import HafeleMQTTCoordinator, KNOWN_OPCODES as MQTT_KNOWN_OPCODES
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
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.LIGHT, Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]

PARALLEL_UPDATES = 0


@dataclass
class MQTTGroup:
    """A Häfele Connect Mesh BLE group with its member device addresses."""

    group_name: str
    group_main_addr: int
    device_addrs: list  # list[int] — device_addr of light members only


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
    mqtt_groups: list = field(default_factory=list)  # list[MQTTGroup]


type HafeleConfigEntry = ConfigEntry[HafeleEntryData]

CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)

# Timeout (seconds) to wait for device discovery via MQTT
_MQTT_DISCOVERY_TIMEOUT = 10


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
                        location=item.get("location", ""),
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
                    location=payload.get("location", ""),
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

    # ------------------------------------------------------------------
    # Groups discovery
    # ------------------------------------------------------------------
    groups_topic = f"{prefix}/groups"
    discovered_groups: list[dict] = []
    groups_event = asyncio.Event()

    @callback
    def _on_groups(msg) -> None:
        try:
            payload = json.loads(msg.payload)
        except (json.JSONDecodeError, TypeError):
            _LOGGER.warning("Invalid MQTT groups payload: %s", msg.payload)
            groups_event.set()
            return
        if isinstance(payload, list):
            discovered_groups.extend(payload)
        elif isinstance(payload, dict):
            discovered_groups.append(payload)
        groups_event.set()

    if direct_client:
        unsubscribe_groups = await direct_client.async_subscribe(groups_topic, _on_groups)
    else:
        unsubscribe_groups = await ha_mqtt.async_subscribe(hass, groups_topic, _on_groups, qos=0)

    try:
        await asyncio.wait_for(groups_event.wait(), timeout=_MQTT_DISCOVERY_TIMEOUT)
    except asyncio.TimeoutError:
        _LOGGER.debug("MQTT groups discovery timed out, continuing without group routing.")
    finally:
        unsubscribe_groups()

    # Build MQTTGroup objects and group-address → coordinator fan-out map
    mqtt_groups: list[MQTTGroup] = []
    group_addr_to_coordinators: dict[int, list[HafeleMQTTCoordinator]] = {}

    for group in discovered_groups:
        try:
            group_addr = int(group["group_main_addr"])
            member_addrs = {int(a) for a in group.get("devices", [])}
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Skipping malformed group entry: %s", err)
            continue
        member_devices = [d for d in light_devices if d.device_addr in member_addrs]
        member_coordinators = [coordinators[d.id] for d in member_devices if d.id in coordinators]
        if not member_coordinators:
            continue
        mqtt_groups.append(MQTTGroup(
            group_name=group["group_name"],
            group_main_addr=group_addr,
            device_addrs=[d.device_addr for d in member_devices],
        ))
        group_addr_to_coordinators[group_addr] = member_coordinators
        _LOGGER.debug(
            "Group 0x%04X '%s' → %d member(s)",
            group_addr, group["group_name"], len(member_coordinators),
        )

    entry.runtime_data = HafeleEntryData(
        coordinators=coordinators,
        devices=light_devices,
        gateways=[],
        prefix=prefix,
        direct_client=direct_client,
        mqtt_groups=mqtt_groups,
    )

    # Subscribe to hafele/rawMessage for BLE Mesh push updates.
    # The gateway publishes Set Unack messages here when a physical device changes
    # state (toggle, dim), giving us a true local_push update path.
    if coordinators:
        # Build reverse map: BLE device_addr (int) → coordinator
        addr_to_coordinator: dict[int, HafeleMQTTCoordinator] = {
            device.device_addr: coordinators[device.id]
            for device in light_devices
        }

        # Deduplication: track (source_addr, sequence_number) of recently seen messages
        _seen_raw: set[tuple[int, int]] = set()

        @callback
        def _on_raw_message(msg) -> None:
            try:
                data = json.loads(msg.payload)
            except (json.JSONDecodeError, TypeError):
                return

            # Parse source address — gateway sends hex string "7FFC" or "0x7FFC"
            raw_source = data.get("source", "")
            try:
                if isinstance(raw_source, int):
                    source_addr = raw_source
                else:
                    src_str = str(raw_source).strip()
                    if src_str.startswith(("0x", "0X")):
                        src_str = src_str[2:]
                    source_addr = int(src_str, 16)
            except (ValueError, TypeError):
                return

            # Deduplicate BLE mesh retransmits by (source, sequence_number)
            seq_num = data.get("sequence_number", -1)
            key = (source_addr, seq_num)
            if key in _seen_raw:
                return
            _seen_raw.add(key)
            if len(_seen_raw) > 100:
                _seen_raw.clear()

            # Normalize opcode early so we can log it in the fallback path
            opcode = data.get("opcode", "").upper()
            if opcode.startswith("0X"):
                opcode = opcode[2:]
            payload_hex = data.get("payload", "")

            # Tier 1 — source lookup: covers Status responses (008204/00824E/…)
            # where source = the light node replying to our Get command.
            coordinator = addr_to_coordinator.get(source_addr)

            # Parse destination once (needed for tiers 2 and 3)
            dest_addr: int | None = None
            if coordinator is None:
                raw_dest = data.get("destination", "")
                try:
                    if isinstance(raw_dest, int):
                        dest_addr = raw_dest
                    else:
                        dest_str = str(raw_dest).strip()
                        if dest_str.startswith(("0x", "0X")):
                            dest_str = dest_str[2:]
                        dest_addr = int(dest_str, 16)
                except (ValueError, TypeError):
                    pass

            # Tier 2 — destination unicast: Set Unack (008203/00824D/…) where a
            # physical switch is the source and the individual light is the destination.
            if coordinator is None and dest_addr is not None:
                coordinator = addr_to_coordinator.get(dest_addr)

            # Tier 3 — group fan-out: destination is a group address (e.g. 008207
            # from a tactile remote). Dispatch to every member coordinator.
            if coordinator is None and dest_addr is not None:
                group_coordinators = group_addr_to_coordinators.get(dest_addr)
                if group_coordinators:
                    for gc in group_coordinators:
                        gc.handle_raw_message(opcode, payload_hex)
                    return

            if coordinator is None:
                if opcode in MQTT_KNOWN_OPCODES:
                    _LOGGER.debug(
                        "rawMessage: known opcode %s from src=0x%s — no matching device (gateway or non-light node)",
                        opcode, data.get("source", "?"),
                    )
                else:
                    _LOGGER.debug(
                        "rawMessage: unknown opcode %s from src=0x%s — ignored",
                        opcode, data.get("source", "?"),
                    )
                return

            coordinator.handle_raw_message(opcode, payload_hex)

        raw_topic = f"{prefix}/rawMessage"
        if direct_client:
            unsubscribe_raw = await direct_client.async_subscribe(raw_topic, _on_raw_message)
        else:
            unsubscribe_raw = await ha_mqtt.async_subscribe(hass, raw_topic, _on_raw_message, qos=0)

        async def _unsub_raw() -> None:
            unsubscribe_raw()

        entry.async_on_unload(_unsub_raw)

        # Initial burst: request state from all devices so they become available
        # immediately without waiting for a physical event.
        for coordinator in coordinators.values():
            hass.async_create_task(coordinator.async_request_state())

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # suggested_area in DeviceInfo is ignored when a device is restored from the
    # deleted_devices cache (e.g. after deleting and re-adding the entry). Explicitly
    # assign the area here for any device that still has none, but never overwrite
    # an area the user has already set.
    device_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)
    for device in light_devices:
        if not device.location:
            continue
        device_entry = device_reg.async_get_device(identifiers={(DOMAIN, device.id)})
        if device_entry is None or device_entry.area_id is not None:
            continue
        area = area_reg.async_get_area_by_name(device.location)
        if area is None:
            area = area_reg.async_create(device.location)
        device_reg.async_update_device(device_entry.id, area_id=area.id)
        _LOGGER.debug("Assigned area '%s' to device '%s'", device.location, device.device_name)

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
            await coordinator.async_shutdown()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Disconnect the direct MQTT client if one was created
        if entry_data.direct_client:
            await entry_data.direct_client.async_disconnect()

    return unload_ok
