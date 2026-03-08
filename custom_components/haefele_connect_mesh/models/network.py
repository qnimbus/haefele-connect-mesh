from contextlib import suppress
from datetime import UTC, datetime
from typing import Any

from ..exceptions import ValidationError
from ..models.device import Device
from ..utils.parse_date import parse_iso_date


class NetworkKey:
    """Represents a network key in the mesh network."""

    def __init__(
        self,
        name: str,
        index: int,
        key: str,
        min_security: str,
        phase: int,
        timestamp: str,
    ) -> None:
        """
        Initialize a NetworkKey instance.

        Args:
            name: Name of the network key
            index: Key index
            key: The key value
            min_security: Minimum security level
            phase: Key phase
            timestamp: Key timestamp

        """
        self._name = name
        self._index = index
        self._key = key
        self._min_security = min_security
        self._phase = phase
        self._timestamp = timestamp

    @property
    def name(self) -> str:
        """Get the network key name."""
        return self._name

    @property
    def index(self) -> int:
        """Get the key index."""
        return self._index

    @property
    def key(self) -> str:
        """Get the key value."""
        return self._key

    @property
    def min_security(self) -> str:
        """Get the minimum security level."""
        return self._min_security

    @property
    def phase(self) -> int:
        """Get the key phase."""
        return self._phase

    @property
    def timestamp(self) -> str:
        """Get the key timestamp."""
        return self._timestamp

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "NetworkKey":
        """Create a NetworkKey instance from dictionary data."""
        try:
            return cls(
                name=data["name"],
                index=int(data["index"]),
                key=data["key"],
                min_security=data["minSecurity"],
                phase=int(data["phase"]),
                timestamp=data["timestamp"],
            )
        except (KeyError, ValueError, TypeError) as e:
            raise ValidationError(f"Invalid network key data: {e!s}") from e


class ApplicationKey:
    """Represents an application key in the mesh network."""

    def __init__(self, name: str, index: int, bound_net_key: int, key: str) -> None:
        """
        Initialize an ApplicationKey instance.

        Args:
            name: Name of the application key
            index: Key index
            bound_net_key: Index of the bound network key
            key: The key value

        """
        self._name = name
        self._index = index
        self._bound_net_key = bound_net_key
        self._key = key

    @property
    def name(self) -> str:
        """Get the application key name."""
        return self._name

    @property
    def index(self) -> int:
        """Get the key index."""
        return self._index

    @property
    def bound_net_key(self) -> int:
        """Get the bound network key index."""
        return self._bound_net_key

    @property
    def key(self) -> str:
        """Get the key value."""
        return self._key

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ApplicationKey":
        """
        Create an ApplicationKey instance from dictionary data.

        Args:
            data: Dictionary containing application key data

        Returns:
            ApplicationKey instance

        Raises:
            ValidationError: If required fields are missing or invalid

        """
        try:
            return cls(
                name=data["name"],
                index=int(data["index"]),
                bound_net_key=int(data["boundNetKey"]),
                key=data["key"],
            )
        except (KeyError, ValueError, TypeError) as e:
            raise ValidationError(f"Invalid application key data: {e!s}") from e


class AddressRange:
    """Represents an address range for provisioners."""

    def __init__(self, low_address: str, high_address: str) -> None:
        """
        Initialize an AddressRange instance.

        Args:
            low_address: Lower bound of the address range
            high_address: Upper bound of the address range

        """
        self._low_address = low_address
        self._high_address = high_address

    @property
    def low_address(self) -> str:
        """Get the lower bound address."""
        return self._low_address

    @property
    def high_address(self) -> str:
        """Get the upper bound address."""
        return self._high_address

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "AddressRange":
        """
        Create an AddressRange instance from dictionary data.

        Args:
            data: Dictionary containing address range data

        Returns:
            AddressRange instance

        Raises:
            ValidationError: If required fields are missing

        """
        try:
            return cls(low_address=data["lowAddress"], high_address=data["highAddress"])
        except KeyError as e:
            raise ValidationError(f"Invalid address range data: {e!s}") from e


class SceneRange:
    """Represents a scene range for provisioners."""

    def __init__(self, first_scene: str, last_scene: str) -> None:
        """
        Initialize a SceneRange instance.

        Args:
            first_scene: First scene in the range
            last_scene: Last scene in the range

        """
        self._first_scene = first_scene
        self._last_scene = last_scene

    @property
    def first_scene(self) -> str:
        """Get the first scene."""
        return self._first_scene

    @property
    def last_scene(self) -> str:
        """Get the last scene."""
        return self._last_scene

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "SceneRange":
        """
        Create a SceneRange instance from dictionary data.

        Args:
            data: Dictionary containing scene range data

        Returns:
            SceneRange instance

        Raises:
            ValidationError: If required fields are missing

        """
        try:
            return cls(first_scene=data["firstScene"], last_scene=data["lastScene"])
        except KeyError as e:
            raise ValidationError(f"Invalid scene range data: {e!s}") from e


class Provisioner:
    """Represents a provisioner in the mesh network."""

    def __init__(
        self,
        provisioner_name: str,
        uuid: str,
        allocated_unicast_range: list[AddressRange],
        allocated_group_range: list[AddressRange],
        allocated_scene_range: list[SceneRange],
    ) -> None:
        """
        Initialize a Provisioner instance.

        Args:
            provisioner_name: Name of the provisioner
            uuid: Unique identifier
            allocated_unicast_range: List of allocated unicast address ranges
            allocated_group_range: List of allocated group address ranges
            allocated_scene_range: List of allocated scene ranges

        """
        self._provisioner_name = provisioner_name
        self._uuid = uuid
        self._allocated_unicast_range = allocated_unicast_range
        self._allocated_group_range = allocated_group_range
        self._allocated_scene_range = allocated_scene_range

    @property
    def provisioner_name(self) -> str:
        """Get the provisioner name."""
        return self._provisioner_name

    @property
    def uuid(self) -> str:
        """Get the UUID."""
        return self._uuid

    @property
    def allocated_unicast_range(self) -> list[AddressRange]:
        """Get the allocated unicast ranges."""
        return self._allocated_unicast_range

    @property
    def allocated_group_range(self) -> list[AddressRange]:
        """Get the allocated group ranges."""
        return self._allocated_group_range

    @property
    def allocated_scene_range(self) -> list[SceneRange]:
        """Get the allocated scene ranges."""
        return self._allocated_scene_range

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Provisioner":
        """
        Create a Provisioner instance from dictionary data.

        Args:
            data: Dictionary containing provisioner data

        Returns:
            Provisioner instance

        Raises:
            ValidationError: If required fields are missing or invalid

        """
        try:
            return cls(
                provisioner_name=data["provisionerName"],
                uuid=data["UUID"],
                allocated_unicast_range=[
                    AddressRange.from_dict(r) for r in data["allocatedUnicastRange"]
                ],
                allocated_group_range=[
                    AddressRange.from_dict(r) for r in data["allocatedGroupRange"]
                ],
                allocated_scene_range=[
                    SceneRange.from_dict(r) for r in data["allocatedSceneRange"]
                ],
            )
        except (KeyError, ValidationError) as e:
            raise ValidationError(f"Invalid provisioner data: {e!s}") from e


class MeshConfiguration:
    """Represents the mesh network configuration."""

    def __init__(
        self,
        id: str,
        version: str,
        mesh_name: str,
        mesh_uuid: str,
        net_keys: list[NetworkKey],
        app_keys: list[ApplicationKey],
        provisioners: list[Provisioner],
    ) -> None:
        """
        Initialize a MeshConfiguration instance.

        Args:
            id: Configuration ID
            version: Schema version
            mesh_name: Name of the mesh network
            mesh_uuid: UUID of the mesh network
            net_keys: List of network keys
            app_keys: List of application keys
            provisioners: List of provisioners

        """
        self._id = id
        self._version = version
        self._mesh_name = mesh_name
        self._mesh_uuid = mesh_uuid
        self._net_keys = net_keys
        self._app_keys = app_keys
        self._provisioners = provisioners

    @property
    def id(self) -> str:
        """Get the configuration ID."""
        return self._id

    @property
    def version(self) -> str:
        """Get the schema version."""
        return self._version

    @property
    def mesh_name(self) -> str:
        """Get the mesh network name."""
        return self._mesh_name

    @property
    def mesh_uuid(self) -> str:
        """Get the mesh network UUID."""
        return self._mesh_uuid

    @property
    def net_keys(self) -> list[NetworkKey]:
        """Get the network keys."""
        return self._net_keys

    @property
    def app_keys(self) -> list[ApplicationKey]:
        """Get the application keys."""
        return self._app_keys

    @property
    def provisioners(self) -> list[Provisioner]:
        """Get the provisioners."""
        return self._provisioners

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MeshConfiguration":
        """
        Create a MeshConfiguration instance from dictionary data.

        Args:
            data: Dictionary containing mesh configuration data

        Returns:
            MeshConfiguration instance

        Raises:
            ValidationError: If required fields are missing or invalid

        """
        try:
            return cls(
                id=data["id"],
                version=data["version"],
                mesh_name=data["meshName"],
                mesh_uuid=data["meshUUID"],
                net_keys=[NetworkKey.from_dict(key) for key in data["netKeys"]],
                app_keys=[ApplicationKey.from_dict(key) for key in data["appKeys"]],
                provisioners=[Provisioner.from_dict(p) for p in data["provisioners"]],
            )
        except KeyError as e:
            raise ValidationError(
                f"Invalid mesh configuration data: Missing field {e!s}"
            ) from e
        except ValidationError as e:
            raise ValidationError(f"Invalid mesh configuration data: {e!s}") from e


class Network:
    """Represents a Häfele Connect Mesh network."""

    def __init__(
        self,
        id: str,
        network_key: str,
        name: str,
        creation_date: datetime,
        update_date: datetime,
        mesh_config: MeshConfiguration | None = None,
        devices: list[Device] | None = None,
    ) -> None:
        """
        Initialize a Network instance.

        Args:
            id: Network ID
            network_key: Network encryption key
            name: User-defined network name
            creation_date: Network creation timestamp
            update_date: Last update timestamp
            mesh_config: Optional mesh network configuration
            devices: Optional list of devices in the network

        """
        self._id = id
        self._network_key = network_key
        self._name = name
        self._creation_date = creation_date
        self._update_date = update_date
        self._mesh_config = mesh_config
        self._devices = devices
        self._last_updated = datetime.now(UTC)

    @property
    def id(self) -> str:
        """Get the network ID."""
        return self._id

    @property
    def network_key(self) -> str:
        """Get the network encryption key."""
        return self._network_key

    @property
    def name(self) -> str:
        """Get the network name."""
        return self._name

    @property
    def creation_date(self) -> datetime:
        """Get the creation date."""
        return self._creation_date

    @property
    def update_date(self) -> datetime:
        """Get the last update date."""
        return self._update_date

    @property
    def mesh_config(self) -> MeshConfiguration | None:
        """Get the mesh configuration."""
        return self._mesh_config

    @property
    def last_updated(self) -> datetime:
        """Get the timestamp of the last update to this network instance."""
        return self._last_updated

    def update_timestamp(self) -> None:
        """Update the last_updated timestamp to current time."""
        self._last_updated = datetime.now(UTC)

    def get_devices(self, devices: list[Device]) -> list[Device]:
        """
        Get all devices associated with this network.

        Args:
            devices: List of Device instances from the API

        Returns:
            List of Device instances belonging to this network

        """
        if self._devices is None:
            # Filter devices for this network
            self._devices = [
                device for device in devices if device.network_id == self._id
            ]
            self.update_timestamp()  # Update timestamp when devices are loaded

        return self._devices

    def get_device_by_id(self, device_id: str) -> Device | None:
        """
        Get a specific device by its unique ID.

        Args:
            device_id: The unique ID of the device to find

        Returns:
            Device instance if found, None otherwise

        Note:
            get_devices() must be called first to populate the device cache

        """
        if self._devices is None:
            return None

        return next(
            (device for device in self._devices if device.id == device_id), None
        )

    def get_devices_by_type(self, device_type: str) -> list[Device]:
        """
        Get all devices of a specific type.

        Args:
            device_type: The type of devices to find (e.g., 'com.haefele.led.rgb')

        Returns:
            List of Device instances of the specified type

        Note:
            get_devices() must be called first to populate the device cache

        """
        if self._devices is None:
            return []

        return [device for device in self._devices if device.type == device_type]

    @property
    def device_types(self) -> set[str]:
        """
        Get all unique device types in this network.

        Returns:
            Set of device type strings

        Note:
            get_devices() must be called first to populate the device cache

        """
        if self._devices is None:
            return set()

        return {device.type for device in self._devices}

    @property
    def lights(self) -> list[Device]:
        """
        Get all light devices in the network.

        Returns:
            List of light Device instances

        Note:
            get_devices() must be called first to populate the device cache

        """
        if self._devices is None:
            return []

        return [device for device in self._devices if device.is_light]

    @property
    def switches(self) -> list[Device]:
        """
        Get all switch devices in the network.

        Returns:
            List of switch Device instances

        Note:
            get_devices() must be called first to populate the device cache

        """
        if self._devices is None:
            return []

        return [device for device in self._devices if device.is_switch]

    @property
    def sensors(self) -> list[Device]:
        """
        Get all sensor devices in the network.

        Returns:
            List of sensor Device instances

        Note:
            get_devices() must be called first to populate the device cache

        """
        if self._devices is None:
            return []

        return [device for device in self._devices if device.is_sensor]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Network":
        """
        Create a Network instance from dictionary data.

        Args:
            data: Dictionary containing network data from API

        Returns:
            Network instance

        Raises:
            ValidationError: If required fields are missing or invalid

        """
        try:
            network = cls(
                id=data["id"],
                network_key=data["networkKey"],
                name=data["name"],
                creation_date=parse_iso_date(data["creationDate"]),
                update_date=parse_iso_date(data["updateDate"]),
                mesh_config=None,
                devices=None,
            )

            if "network" in data:
                with suppress(Exception):
                    network._mesh_config = MeshConfiguration.from_dict(
                        {"networkId": data["id"], **data["network"]}
                    )

            return network

        except KeyError as e:
            raise ValidationError(
                f"Missing required field in network data: {e!s}"
            ) from e

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the network instance to a dictionary.

        Returns:
            Dictionary representation of the network

        """
        return {
            "id": self._id,
            "networkKey": self._network_key,
            "name": self._name,
            "creationDate": self._creation_date.isoformat(),
            "updateDate": self._update_date.isoformat(),
        }
