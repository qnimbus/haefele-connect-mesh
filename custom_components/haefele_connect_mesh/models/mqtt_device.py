"""MQTT device model for Häfele Connect Mesh."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Optional


@dataclass
class MQTTDevice:
    """Represents a Häfele device discovered via MQTT.

    Provides the same interface as the cloud Device model so that
    platform entities (light, sensor, binary_sensor) can work with
    both cloud and MQTT devices without branching.
    """

    device_name: str
    device_addr: int
    device_types: list[str]
    _last_updated: datetime = field(
        default_factory=lambda: datetime.now(UTC), repr=False
    )

    @property
    def id(self) -> str:
        """Return the unique device identifier (BLE address as string)."""
        return str(self.device_addr)

    @property
    def name(self) -> str:
        """Return the device name."""
        return self.device_name

    @property
    def is_light(self) -> bool:
        """Return True if the device is a controllable light."""
        types_lower = {t.lower() for t in self.device_types}
        return bool(types_lower & {"light", "multiwhite", "rgb"})

    @property
    def supports_hsl(self) -> bool:
        """Return True if the device supports RGB/HSL color."""
        return any(t.lower() == "rgb" for t in self.device_types)

    @property
    def supports_color_temp(self) -> bool:
        """Return True if the device supports color temperature."""
        return any(t.lower() == "multiwhite" for t in self.device_types)

    @property
    def bootloader_version(self) -> Optional[str]:
        """Firmware version — not available via MQTT."""
        return None

    @property
    def network_id(self) -> Optional[str]:
        """Network ID — not available via MQTT."""
        return None

    @property
    def type(self) -> None:
        """Device type enum — cloud-specific, not available via MQTT."""
        return None

    @property
    def last_updated(self) -> datetime:
        """Return the timestamp of the last status update."""
        return self._last_updated

    def update_timestamp(self) -> None:
        """Update the last_updated timestamp to now."""
        self._last_updated = datetime.now(UTC)
