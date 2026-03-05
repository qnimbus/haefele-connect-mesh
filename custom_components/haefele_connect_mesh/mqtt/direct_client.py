"""Direct aiomqtt client wrapper for use without HA's MQTT integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

try:
    import aiomqtt
    AIOMQTT_AVAILABLE = True
except ImportError:
    AIOMQTT_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)


class DirectMQTTClient:
    """Wraps aiomqtt for a long-lived MQTT connection outside HA's MQTT component.

    Used when the user configures a custom broker instead of the one managed
    by HA's MQTT integration.
    """

    def __init__(
        self,
        broker: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Store broker credentials; call async_connect to actually connect."""
        if not AIOMQTT_AVAILABLE:
            raise ImportError(
                "aiomqtt is required for direct MQTT connections. "
                "Add 'aiomqtt' to the integration requirements."
            )
        self._broker = broker
        self._port = port
        self._username = username or None
        self._password = password or None
        self._client: aiomqtt.Client | None = None
        self._connected = False
        self._subscriptions: dict[str, list[Callable]] = {}
        self._message_listener_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def async_connect(self) -> None:
        """Open the connection and start the background message listener."""
        self._client = aiomqtt.Client(
            hostname=self._broker,
            port=self._port,
            username=self._username,
            password=self._password,
        )
        try:
            await self._client.__aenter__()
        except Exception as err:
            raise ConnectionError(
                f"Cannot connect to MQTT broker {self._broker}:{self._port}: {err}"
            ) from err

        self._connected = True
        self._message_listener_task = asyncio.create_task(self._message_listener())
        _LOGGER.info("Direct MQTT client connected to %s:%d", self._broker, self._port)

    async def async_disconnect(self) -> None:
        """Cancel the listener task and close the connection."""
        if self._message_listener_task:
            self._message_listener_task.cancel()
            try:
                await self._message_listener_task
            except asyncio.CancelledError:
                pass
            self._message_listener_task = None

        if self._client:
            try:
                await self._client.__aexit__(None, None, None)
            except Exception as err:
                _LOGGER.debug("Error during MQTT disconnect: %s", err)
            self._client = None

        self._connected = False
        _LOGGER.debug("Direct MQTT client disconnected")

    # ------------------------------------------------------------------
    # Pub/sub
    # ------------------------------------------------------------------

    async def async_subscribe(self, topic: str, callback: Callable) -> Callable:
        """Subscribe to *topic* and return a sync unsubscribe callable."""
        if not self._client or not self._connected:
            raise ConnectionError("MQTT client is not connected")

        await self._client.subscribe(topic, qos=0)

        if topic not in self._subscriptions:
            self._subscriptions[topic] = []
        self._subscriptions[topic].append(callback)

        def unsubscribe() -> None:
            if topic in self._subscriptions:
                try:
                    self._subscriptions[topic].remove(callback)
                except ValueError:
                    pass
                if not self._subscriptions[topic]:
                    del self._subscriptions[topic]

        return unsubscribe

    async def async_publish(self, topic: str, payload: str) -> None:
        """Publish *payload* to *topic*."""
        if not self._client or not self._connected:
            raise ConnectionError("MQTT client is not connected")
        await self._client.publish(topic, payload.encode() if isinstance(payload, str) else payload)

    # ------------------------------------------------------------------
    # Background message listener
    # ------------------------------------------------------------------

    async def _message_listener(self) -> None:
        """Dispatch incoming messages to registered callbacks."""
        try:
            async for msg in self._client.messages:
                topic = str(msg.topic)
                callbacks = list(self._subscriptions.get(topic, []))
                for callback in callbacks:
                    try:
                        callback(msg)
                    except Exception as err:
                        _LOGGER.error(
                            "Error in MQTT callback for topic %s: %s", topic, err
                        )
        except asyncio.CancelledError:
            _LOGGER.debug("MQTT message listener cancelled")
        except Exception as err:
            _LOGGER.error("MQTT message listener error: %s", err)
