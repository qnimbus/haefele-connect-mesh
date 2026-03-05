"""MQTT-based coordinator for Häfele Connect Mesh devices."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..const import DOMAIN, MIN_KELVIN, MAX_KELVIN
from ..models.mqtt_device import MQTTDevice
from .direct_client import DirectMQTTClient

_LOGGER = logging.getLogger(__name__)


class HafeleMQTTCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that subscribes to MQTT status topics and optionally polls."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: MQTTDevice,
        topic_prefix: str,
        direct_client: DirectMQTTClient | None = None,
    ) -> None:
        """Initialize the MQTT coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=device.name,
            update_interval=None,
        )
        self.device = device
        self._prefix = topic_prefix
        self._direct_client = direct_client
        self._unsubscribe: Callable | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_setup(self) -> None:
        """Subscribe to MQTT status topic and request initial state."""
        status_topic = f"{self._prefix}/lights/{self.device.device_name}/status"

        if self._direct_client:
            self._unsubscribe = await self._direct_client.async_subscribe(
                status_topic, self._handle_message
            )
        else:
            self._unsubscribe = await mqtt.async_subscribe(
                self.hass,
                status_topic,
                self._handle_message,
                qos=0,
            )
        _LOGGER.debug("Subscribed to MQTT topic: %s", status_topic)

        # Request initial state
        await self._publish_get("powerGet")
        await self._publish_get("lightnessGet")

    async def async_unsubscribe(self) -> None:
        """Cancel the MQTT subscription."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    async def async_request_state(self) -> None:
        """Request current device state from the gateway."""
        await self._publish_get("powerGet")
        await self._publish_get("lightnessGet")

    # ------------------------------------------------------------------
    # MQTT message handling
    # ------------------------------------------------------------------

    @callback
    def _handle_message(self, msg: mqtt.ReceiveMessage) -> None:
        """Process an incoming MQTT status message."""
        try:
            payload = json.loads(msg.payload)
        except (json.JSONDecodeError, TypeError):
            _LOGGER.warning(
                "Received invalid JSON on %s: %s", msg.topic, msg.payload
            )
            return

        normalized = self._normalize(payload)
        if not normalized:
            return

        # Merge into existing state so partial updates don't lose fields
        current_state = (self.data or {}).get("state", {})
        merged = {**current_state, **normalized}

        self.device.update_timestamp()
        self.async_set_updated_data({"state": merged})

        _LOGGER.debug(
            "MQTT update for %s: %s → state=%s",
            self.device.name,
            payload,
            merged,
        )

    @staticmethod
    def _normalize(payload: dict[str, Any]) -> dict[str, Any]:
        """Normalise MQTT payload values to internal mesh-scale format.

        Returns a partial state dict containing only the keys present in
        the payload.
        """
        result: dict[str, Any] = {}

        if "onoff" in payload:
            raw = payload["onoff"]
            if isinstance(raw, bool):
                result["power"] = raw
            elif isinstance(raw, int):
                result["power"] = bool(raw)
            elif isinstance(raw, str):
                result["power"] = raw.lower() == "on"

        if "lightness" in payload:
            raw = payload["lightness"]
            try:
                v = float(raw)
                # API delivers 0.0–1.0; convert to mesh 0–65535
                result["lightness"] = round(v * 65535)
                result["lastLightness"] = result["lightness"]
            except (ValueError, TypeError):
                pass

        if "temperature" in payload:
            raw = payload["temperature"]
            try:
                kelvin = float(raw)
                result["temperature"] = round(
                    (kelvin - MIN_KELVIN) / (MAX_KELVIN - MIN_KELVIN) * 65535
                )
            except (ValueError, TypeError):
                pass

        if "hue" in payload:
            try:
                result["hue"] = float(payload["hue"])
            except (ValueError, TypeError):
                pass

        if "saturation" in payload:
            try:
                result["saturation"] = float(payload["saturation"])
            except (ValueError, TypeError):
                pass

        return result

    # ------------------------------------------------------------------
    # Command methods (uniform interface shared with cloud coordinator)
    # ------------------------------------------------------------------

    async def async_set_power(self, on: bool) -> None:
        """Publish a power command."""
        await self._publish_command("power", on)

    async def async_set_lightness(self, value: float) -> None:
        """Publish a lightness command (0.0–1.0)."""
        await self._publish_command("lightness", value)

    async def async_set_temperature(self, kelvin: int) -> None:
        """Publish a color-temperature command (Kelvin)."""
        await self._publish_command("temperature", kelvin)

    async def async_set_hsl(self, hue: float, saturation: float) -> None:
        """Publish an HSL command."""
        await self._publish_command("hsl", {"hue": hue, "saturation": saturation})

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _publish_command(self, command: str, payload: Any) -> None:
        """Publish a command to the device's MQTT topic."""
        topic = f"{self._prefix}/lights/{self.device.device_name}/{command}"
        if isinstance(payload, bool):
            payload_str = json.dumps(payload)  # True → "true", False → "false"
        elif isinstance(payload, (dict, list)):
            payload_str = json.dumps(payload)
        else:
            payload_str = str(payload)
        if self._direct_client:
            await self._direct_client.async_publish(topic, payload_str)
        else:
            await mqtt.async_publish(self.hass, topic, payload_str)

    async def _publish_get(self, command: str) -> None:
        """Publish a get-request command (no value)."""
        topic = f"{self._prefix}/lights/{self.device.device_name}/{command}"
        if self._direct_client:
            await self._direct_client.async_publish(topic, "")
        else:
            await mqtt.async_publish(self.hass, topic, "")

    # ------------------------------------------------------------------
    # Required by DataUpdateCoordinator
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:  # type: ignore[override]
        """Poll the device state via MQTT get-requests."""
        await self._publish_get("powerGet")
        await self._publish_get("lightnessGet")
        return self.data or {}
