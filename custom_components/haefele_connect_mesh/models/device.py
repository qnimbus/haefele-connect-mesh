"""Device models for the Häfele Connect Mesh API."""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from ..exceptions import ValidationError


@dataclass
class Element:
    """
    Represents a device element in the mesh network.

    Elements are the basic building blocks of mesh devices, each representing
    a controllable component of the device.
    """

    device_id: str
    unicast_address: int
    models: list[int]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Element":
        """
        Create an Element instance from dictionary data.

        Args:
            data: Dictionary containing element data

        Returns:
            Element instance

        Raises:
            ValidationError: If required fields are missing or invalid

        """
        try:
            return cls(
                device_id=data["deviceId"],
                unicast_address=int(data["unicastAddress"]),
                models=[int(model) for model in data["models"]],
            )
        except (KeyError, ValueError, TypeError) as e:
            raise ValidationError(f"Invalid element data: {e!s}")


class DeviceType(Enum):
    """Enum for Häfele Connect Mesh device types."""

    # Ledvance devices
    LEDVANCE_SOCKET = "de.ledvance.socket"

    # Jung devices
    JUNG_SOCKET = "de.jung.socket"

    # Nimbus devices
    NIMBUS_PAD_DIRECT = "de.nimbus.lighting.pad.direct"
    NIMBUS_PAD_INDIRECT = "de.nimbus.lighting.pad.indirect"
    NIMBUS_LEGGERA = "de.nimbus.leggera"
    NIMBUS_Q_CLASSIC_MW = "de.nimbus.q.classic.multiwhite"
    NIMBUS_Q_CUBIC_MW = "de.nimbus.q.cubic.multiwhite"
    NIMBUS_Q_FOUR_MW = "de.nimbus.q.four.multiwhite"
    NIMBUS_ZEN = "de.nimbus.zen"

    # Häfele furniture devices
    HAEFELE_TVLIFT = "com.haefele.tvlift"
    HAEFELE_MOTOR = "com.haefele.motor"
    HAEFELE_WARDROBE_LIFT = "com.haefele.lift.wardrobe"
    HAEFELE_PUSHLOCK = "com.haefele.pushlock"
    HAEFELE_PUSHLOCK_5S = "com.haefele.pushlock.5s"

    # Häfele lighting devices
    HAEFELE_LED_RGB = "com.haefele.led.rgb"
    HAEFELE_LED_RGB_SPOT = "com.haefele.led.rgb.spot"
    HAEFELE_LED_MW_SPOT = "com.haefele.led.multiwhite.spot"
    HAEFELE_LED_MW_2200K = "com.haefele.led.multiwhite.2200K"
    HAEFELE_LED_MW_2700K = "com.haefele.led.multiwhite.2700K"
    HAEFELE_LED_MW_2WIRE_MONO_SPOT = "com.haefele.led.multiwhite.2wire.monochrome.spot"
    HAEFELE_LED_MW_2WIRE_MONO_STRIPE = (
        "com.haefele.led.multiwhite.2wire.monochrome.stripe"
    )
    HAEFELE_LED_MW_2WIRE_MW_SPOT = "com.haefele.led.multiwhite.2wire.mw.spot"
    HAEFELE_LED_MW_2WIRE_MW_STRIPE = "com.haefele.led.multiwhite.2wire.mw.stripe"
    HAEFELE_LED_WHITE = "com.haefele.led.white"
    HAEFELE_LED_WHITE_STRIP = "com.haefele.led.white.strip"

    # Häfele other devices
    HAEFELE_SOCKET = "com.haefele.socket"
    HAEFELE_MOTION_SENSOR = "com.haefele.motion.sensor"
    HAEFELE_FURNITURE_SENSOR_MAINS = "com.haefele.furniture.sensor.mains"
    HAEFELE_FURNITURE_SENSOR_BATTERY = "com.haefele.furniture.sensor.battery"
    HAEFELE_WALLCONTROLLER = "com.haefele.wallcontroller.actuator"
    HAEFELE_Q_DEV_MW = "com.haefele.q.dev.multiwhite"
    HAEFELE_Q_DEV_MONO = "com.haefele.q.dev.monochrome"

    # Generic devices
    GENERIC_LED_MW = "com.generic.led.multiwhite"
    GENERIC_LED_WHITE = "com.generic.led.white"
    GENERIC_LED_RGB = "com.generic.led.rgb"
    GENERIC_LEVEL = "com.generic.level"
    NORDIC_DEVKIT_LEVEL = "com.nordic.devkit.level"

    @property
    def is_light(self) -> bool:
        """Check if the device type is a light."""
        return any(
            self.value.startswith(prefix)
            for prefix in ["com.haefele.led", "com.generic.led", "de.nimbus"]
        )

    @property
    def supports_color_temp(self) -> bool:
        """Check if the device type supports color temperature."""
        return any(
            self.value.startswith(prefix)
            for prefix in [
                "com.haefele.led.multiwhite",
                "de.nimbus.q",
                "com.haefele.q.dev.multiwhite",
                "com.generic.led.multiwhite",
            ]
        )

    @property
    def supports_hsl(self) -> bool:
        """Check if the device type supports Hue, Saturation and lightness."""
        return any(
            self.value.startswith(prefix)
            for prefix in ["com.haefele.led.rgb", "com.generic.led.rgb"]
        )

    @property
    def is_socket(self) -> bool:
        """Check if the device type is a socket."""
        return any(
            self.value.startswith(prefix)
            for prefix in ["de.ledvance.socket", "com.haefele.socket", "de.jung.socket"]
        )

    @property
    def manufacturer(self) -> str:
        """Get the manufacturer based on the device type prefix."""
        if self.value.startswith("de.ledvance."):
            return "LEDVANCE"
        if self.value.startswith("de.jung."):
            return "JUNG"
        if self.value.startswith("de.nimbus."):
            return "Nimbus"
        if self.value.startswith("com.haefele."):
            return "Häfele"
        if self.value.startswith("com.generic."):
            return "Generic"
        return "Unknown"

    @classmethod
    def from_str(cls, type_str: str) -> "DeviceType":
        """Create DeviceType from string value."""
        try:
            return cls(type_str)
        except ValueError:
            raise ValidationError(f"Invalid device type: {type_str}")


class Device:
    """
    Represents a Häfele Connect Mesh device.

    Attributes:
        network_id: UUID of the network the device belongs to
        unicast_address: Device mesh address
        id: Object ID
        name: User-defined device name
        description: Device description
        ble_address: Bluetooth address
        mac_bytes: MAC address bytes
        bootloader_version: Device firmware version
        type: Device type identifier (e.g., 'com.haefele.led.rgb')
        unique_id: Unique device identifier
        device_key: Device encryption key
        elements: List of device mesh elements

    """

    def __init__(
        self,
        network_id: str,
        unicast_address: int,
        id: str,
        name: str,
        description: str | None,
        ble_address: str,
        mac_bytes: str,
        bootloader_version: str,
        type: str,
        unique_id: str,
        device_key: str,
        elements: list[Element],
    ) -> None:
        """
        Initialize a Device instance.

        Args:
            network_id: UUID of the network the device belongs to
            unicast_address: Device mesh address
            id: Object ID
            name: User-defined device name
            description: Device description
            ble_address: Bluetooth address
            mac_bytes: MAC address bytes
            bootloader_version: Device firmware version
            type: Device type identifier
            unique_id: Unique device identifier
            device_key: Device encryption key
            elements: List of device mesh elements

        """
        self._network_id = network_id
        self._unicast_address = unicast_address
        self._id = id
        self._name = name
        self._description = description
        self._ble_address = ble_address
        self._mac_bytes = mac_bytes
        self._bootloader_version = bootloader_version
        self._type = DeviceType.from_str(type)
        self._unique_id = unique_id
        self._device_key = device_key
        self._elements = elements
        self._last_updated = datetime.now(UTC)

    @property
    def network_id(self) -> str:
        """Get the network ID."""
        return self._network_id

    @property
    def unicast_address(self) -> int:
        """Get the unicast address."""
        return self._unicast_address

    @property
    def id(self) -> str:
        """Get the device ID (alias for unique_id)."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Get the device name."""
        return self._name

    @property
    def description(self) -> str | None:
        """Get the device description."""
        return self._description

    @property
    def ble_address(self) -> str:
        """Get the Bluetooth address."""
        return self._ble_address

    @property
    def mac_bytes(self) -> str:
        """Get the MAC address bytes."""
        return self._mac_bytes

    @property
    def bootloader_version(self) -> str:
        """Get the bootloader version."""
        return self._bootloader_version

    @property
    def type(self) -> DeviceType:
        """Get the device type."""
        return self._type

    @property
    def device_key(self) -> str:
        """Get the device key."""
        return self._device_key

    @property
    def elements(self) -> list[Element]:
        """Get the device elements."""
        return self._elements

    @property
    def last_updated(self) -> datetime:
        """Get the timestamp of the last update to this device instance."""
        return self._last_updated

    def update_timestamp(self) -> None:
        """Update the last_updated timestamp to current time."""
        self._last_updated = datetime.now(UTC)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Device":
        """
        Create a Device instance from dictionary data.

        Args:
            data: Dictionary containing device data from API

        Returns:
            Device instance

        Raises:
            ValidationError: If required fields are missing or invalid

        """
        try:
            return cls(
                network_id=data["networkId"],
                unicast_address=int(data["unicastAddress"]),
                id=data["id"],
                name=data["name"],
                description=data.get("description"),
                ble_address=data["bleAddress"],
                mac_bytes=data["macBytes"],
                bootloader_version=data["bootloaderVersion"],
                type=data["type"],
                unique_id=data["uniqueId"],
                device_key=data["deviceKey"],
                elements=[Element.from_dict(elem) for elem in data["elements"]],
            )
        except (KeyError, ValueError) as e:
            raise ValidationError(f"Invalid device data: {e!s}")

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the device instance to a dictionary.

        Returns:
            Dictionary representation of the device

        """
        return {
            "networkId": self._network_id,
            "unicastAddress": self._unicast_address,
            "id": self._id,
            "name": self._name,
            "description": self._description,
            "bleAddress": self._ble_address,
            "macBytes": self._mac_bytes,
            "bootloaderVersion": self._bootloader_version,
            "type": self._type.value,
            "uniqueId": self._unique_id,
            "deviceKey": self._device_key,
            "elements": [
                {
                    "deviceId": elem.device_id,
                    "unicastAddress": elem.unicast_address,
                    "models": elem.models,
                }
                for elem in self._elements
            ],
        }

    @property
    def is_light(self) -> bool:
        """
        Check if the device is a light.

        Returns:
            bool: True if device is a light type

        """
        return self._type.is_light

    @property
    def is_switch(self) -> bool:
        """
        Check if the device is a switch.

        Returns:
            bool: True if device is a switch type

        """
        return self._type == "com.haefele.switch"

    @property
    def is_sensor(self) -> bool:
        """
        Check if the device is a sensor.

        Returns:
            bool: True if device is a sensor type

        """
        return self._type.startswith("com.haefele.sensor")

    @property
    def supports_color_temp(self) -> bool:
        """Check if the device supports color temperature."""
        return self._type.supports_color_temp

    @property
    def supports_hsl(self) -> bool:
        """Check if the device supports RGB color."""
        return self._type.supports_hsl

    @property
    def is_socket(self) -> bool:
        """
        Check if the device is a socket.

        Returns:
            bool: True if device is a socket type

        """
        return self._type.is_socket
