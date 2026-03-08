import asyncio
import json
import logging
from typing import Any

import aiohttp

from ..exceptions import HafeleAPIError, ValidationError
from ..models.device import Device
from ..models.gateway import Gateway
from ..models.network import Network
from ..utils.rate_limit import rate_limit
from ..utils.retry import retry_with_backoff
from .endpoints import BASE_URL, Endpoints

logger = logging.getLogger(__name__)


class HafeleClient:
    """Client for interacting with the Häfele Connect Mesh API."""

    def __init__(
        self, api_key: str, session: aiohttp.ClientSession, timeout: int = 30
    ) -> None:
        """
        Initialize the API client.

        Args:
            api_key: API key for authentication
            session: aiohttp ClientSession instance for making HTTP requests
            timeout: Default request timeout in seconds (default: 30)

        """
        self._api_key = api_key
        self._base_url = BASE_URL
        self._timeout = timeout
        self._session = session
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        logger.debug("Initialized HafeleClient with base URL: %s", self._base_url)

    @retry_with_backoff(base_delay=0.5, max_delay=4.0, jitter_range=0.5)
    async def _request(
        self, method: str, endpoint: str, timeout: int | None = None, **kwargs: Any
    ) -> aiohttp.ClientResponse:
        """
        Make an HTTP request to the API.

        Args:
            method: HTTP method (get, post, put, etc.)
            endpoint: API endpoint to call
            timeout: Request timeout in seconds (uses default if not specified)
            **kwargs: Additional arguments to pass to the request

        Returns:
            Response from the API

        Raises:
            HafeleAPIError: If the request fails

        """
        timeout = timeout or self._timeout
        url = f"{self._base_url}{endpoint}"

        # Merge default headers with any request-specific headers
        headers = dict(self._headers)
        if "headers" in kwargs:
            headers.update(kwargs.pop("headers"))

        try:
            response = await self._session.request(
                method=method, url=url, headers=headers, timeout=timeout, **kwargs
            )
            response.raise_for_status()
            return response

        except Exception as e:
            status_code = None
            error_data = {}

            # Handle timeout specifically
            if isinstance(e, asyncio.TimeoutError):
                raise HafeleAPIError(
                    message=f"Request timed out after {timeout} seconds",
                    status_code=None,
                    error_code="TIMEOUT",
                ) from e

            # Handle aiohttp client errors
            if isinstance(e, aiohttp.ClientResponseError):
                status_code = getattr(e, "status", None)
                error_data = dict(getattr(e, "headers", {}))
                error_data["message"] = getattr(e, "message", "")

            raise HafeleAPIError(
                message=(
                    f"Request failed. Method: {method.upper()}, URL: {url},"
                    f" HTTP Status: {status_code},"
                    f" Error: {error_data.get('message')}"
                ),
                status_code=status_code,
                error_code=error_data.get("message"),
                response=error_data,
            ) from e

    async def _get(self, endpoint: str, **kwargs: Any) -> aiohttp.ClientResponse:
        """Make a GET request to the API."""
        return await self._request("get", endpoint, **kwargs)

    async def _post(self, endpoint: str, **kwargs: Any) -> aiohttp.ClientResponse:
        """Make a POST request to the API."""
        return await self._request("post", endpoint, **kwargs)

    async def _put(self, endpoint: str, **kwargs: Any) -> aiohttp.ClientResponse:
        """Make a PUT request to the API."""
        return await self._request("put", endpoint, **kwargs)

    async def _delete(self, endpoint: str, **kwargs: Any) -> aiohttp.ClientResponse:
        """Make a DELETE request to the API."""
        return await self._request("delete", endpoint, **kwargs)

    async def get_networks(self) -> list[Network]:
        """
        Fetch all available networks.

        Returns:
            List of Network model instances containing network details.

        Raises:
            HafeleAPIError: If the API request fails.
            AuthenticationError: If API key is invalid.

        """
        logger.debug("Fetching networks")

        response = await self._get(Endpoints.NETWORKS.value)
        networks_data = await response.json()

        logger.debug("Successfully fetched network data")
        logger.debug("Network response data: %s", networks_data)

        # Convert to list if single dict is returned
        if isinstance(networks_data, dict):
            networks_data = [networks_data]

        # Fetch network details for each network
        return [
            await self.get_network_details(network["id"]) for network in networks_data
        ]

    async def get_gateways(self) -> list[Gateway]:
        """Fetch all available gateways."""
        response = await self._get(Endpoints.GATEWAYS.value)
        gateways_data = await response.json()

        logger.debug("Successfully fetched gateways data")
        logger.debug("Gateways response data: %s", gateways_data)

        if isinstance(gateways_data, dict):
            gateways_data = [gateways_data]

        return [Gateway.from_dict(gateway) for gateway in gateways_data]

    async def gateway_ping(self, gateway_id: str) -> tuple[bool, int | None]:
        """
        Ping a gateway to check its connectivity and response time.

        Args:
            gateway_id: The ID of the gateway to ping

        Returns:
            Tuple of (success, response_time_ms)
            - success: Boolean indicating if ping was successful
            - response_time_ms: Response time in milliseconds, or None if ping failed

        Raises:
            HafeleAPIError: If the API request fails
            ValidationError: If gateway_id is invalid

        """
        try:
            endpoint = Endpoints.GATEWAY_PING.value.format(id=gateway_id)
            logger.debug("Pinging gateway %s", gateway_id)

            response = await self._get(endpoint)
            data = await response.json()

            success = data.get("success", False)
            response_time = data.get("time") if success else None

            logger.debug(
                "Gateway ping result - Success: %s, Response time: %sms",
                success,
                response_time,
            )

            return success, response_time

        except HafeleAPIError as e:
            logger.error("Failed to ping gateway %s: %s", gateway_id, str(e))
            raise
        except Exception as e:
            logger.error("Unexpected error pinging gateway %s: %s", gateway_id, str(e))
            raise HafeleAPIError(
                message=f"Failed to ping gateway: {e!s}", error_code="PING_FAILED"
            ) from e

    async def get_network_details(self, network_id: str) -> Network:
        """
        Fetch information about a specific network.

        Args:
            network_id: The ID of the network to fetch

        Returns:
            Network model instance containing network details.

        Raises:
            HafeleAPIError: If the API request fails.
            AuthenticationError: If API key is invalid.
            ValidationError: If network_id is invalid.

        """
        endpoint = Endpoints.NETWORK_DETAIL.format(id=network_id)
        logger.debug("Fetching network details from endpoint: %s", endpoint)

        response = await self._get(endpoint)
        network_data = await response.json()

        def recursive_json_decode(data: Any) -> Any:
            if isinstance(data, dict):
                for key, value in data.items():
                    if isinstance(value, str):
                        try:
                            decoded_value = json.loads(value)
                            data[key] = recursive_json_decode(decoded_value)
                        except (json.JSONDecodeError, TypeError):
                            pass
                    else:
                        data[key] = recursive_json_decode(value)
            elif isinstance(data, list):
                for index, item in enumerate(data):
                    data[index] = recursive_json_decode(item)
            return data

        network_data = recursive_json_decode(network_data)

        logger.debug("Successfully fetched network data for ID: %s", network_id)
        logger.debug(
            "Network response data (truncated): %s",
            {k: (v if k != "network" else "...") for k, v in network_data.items()},
        )

        return Network.from_dict(network_data)

    async def get_devices(self) -> list[Device]:
        """
        Fetch all available devices.

        Returns:
            List of Device model instances containing device details.

        Raises:
            HafeleAPIError: If the API request fails.
            AuthenticationError: If API key is invalid.
            ValidationError: If device data is invalid.

        """
        logger.debug("Fetching devices from endpoint: %s", Endpoints.DEVICES.value)

        try:
            response = await self._get(Endpoints.DEVICES.value)
            devices_data = await response.json()
            logger.debug("Successfully fetched devices data")
            logger.debug("Devices response data: %s", devices_data)

            # Convert to list if single dict is returned
            if isinstance(devices_data, dict):
                devices_data = [devices_data]

            # Convert each device dictionary to a Device instance
            devices = [Device.from_dict(device) for device in devices_data]
            logger.debug("Converted %d devices to Device models", len(devices))

            return devices

        except ValidationError as e:
            logger.error("Failed to parse device data: %s", str(e))
            raise
        except HafeleAPIError:
            # Re-raise since _get already handles proper error wrapping
            raise

    async def get_devices_for_network(self, network_id: str) -> list[Device]:
        """
        Fetch all devices belonging to a specific network.

        Args:
            network_id: The ID of the network to fetch devices for

        Returns:
            List of Device model instances belonging to the specified network.

        Raises:
            HafeleAPIError: If the API request fails.
            AuthenticationError: If API key is invalid.
            ValidationError: If device data is invalid.

        """
        logger.debug("Fetching devices for network: %s", network_id)

        devices = await self.get_devices()
        network_devices = [
            device for device in devices if device.network_id == network_id
        ]

        logger.debug(
            "Found %d devices for network %s", len(network_devices), network_id
        )
        return network_devices

    async def get_device_details(self, device_id: str) -> Device:
        """
        Fetch detailed information about a specific device.

        Args:
            device_id: The unique ID of the device to fetch

        Returns:
            Device model instance containing device details.

        Raises:
            HafeleAPIError: If the API request fails.
            AuthenticationError: If API key is invalid.
            ValidationError: If device_id is invalid or response data is malformed.

        """
        endpoint = f"{Endpoints.DEVICE_DETAIL.format(id=device_id)}"
        logger.debug("Fetching device details from endpoint: %s", endpoint)

        try:
            response = await self._get(endpoint)
            device_data = await response.json()
            logger.debug("Successfully fetched device data for ID: %s", device_id)
            logger.debug("Device response data: %s", device_data)

            # Convert response data to Device model
            try:
                device = Device.from_dict(device_data)
                logger.debug("Successfully converted device data to Device model")
                return device

            except ValidationError as e:
                logger.error("Failed to parse device data: %s", str(e))
                raise ValidationError(
                    f"Invalid device data received from API: {e!s}"
                ) from e

        except HafeleAPIError:
            # Re-raise since _get already handles proper error wrapping
            raise

    async def get_device_details_from_device(self, device: Device) -> Device:
        """
        Fetch detailed information about a device using a Device instance.

        This is a convenience method that extracts the device ID and calls
        get_device_details.

        Args:
            device: Device instance to get details for

        Returns:
            Device model instance containing updated device details.

        Raises:
            HafeleAPIError: If the API request fails.
            AuthenticationError: If API key is invalid.
            ValidationError: If device data is invalid.

        """
        return await self.get_device_details(device.id)

    @rate_limit(min_interval=1.0)
    async def get_device_status(self, device_id: str) -> dict[str, Any]:
        """
        Fetch the current status of a specific device.

        Args:
            device_id: The unique ID of the device to check

        Returns:
            Dictionary containing device status information.
            Example for a light:
            {
                "power": "on",
                "lightness": 0.75,
                "temperature": 4000,
                "online": true
            }

        Raises:
            HafeleAPIError: If the API request fails.
            AuthenticationError: If API key is invalid.
            ValidationError: If device_id is invalid.

        """
        endpoint = f"{Endpoints.DEVICE_STATUS.format(id=device_id)}"
        logger.debug("Fetching device status from endpoint: %s", endpoint)

        try:
            response = await self._get(endpoint)
            status_data = await response.json()

            logger.debug("Successfully fetched status for device: %s", device_id)
            logger.debug("Device status data: %s", status_data)

            # Validate that we received a proper status response
            if not isinstance(status_data, dict):
                raise ValidationError(
                    f"Invalid status response format for device {device_id}"
                )

            if "state" not in status_data:
                raise ValidationError(
                    f"Missing state data in status response for device {device_id}"
                )

            return status_data

        except HafeleAPIError as e:
            logger.debug(
                "Failed to fetch device status. Device ID: %s, Status: %s, Error: %s",
                device_id,
                e.status_code,
                e.error_code,
            )
            raise
        except ValidationError as e:
            logger.debug("Invalid device status data: %s", str(e))
            raise

    async def get_device_status_from_device(self, device: Device) -> dict[str, Any]:
        """
        Fetch the current status of a device using a Device instance.

        This is a convenience method that extracts the device ID and calls
        get_device_status.

        Args:
            device: Device instance to get status for

        Returns:
            Dictionary containing device status information

        Raises:
            HafeleAPIError: If the API request fails.
            AuthenticationError: If API key is invalid.
            ValidationError: If device data is invalid.

        """
        return await self.get_device_status(device.id)

    async def set_power(
        self,
        device: Device,
        power: bool,
        acknowledged: bool = True,
        retries: int = 0,
        timeout_ms: int = 10000,
    ) -> None:
        """
        Set the power state of a device.

        Args:
            device: Device instance to control
            power: True for on, False for off
            acknowledged: Whether to wait for acknowledgment (default: True)
            retries: Number of mesh-level retries (default: 0)
            timeout_ms: Mesh operation timeout in milliseconds (default: 10000)

        Raises:
            HafeleAPIError: If the API request fails
            ValidationError: If device data is invalid

        """
        logger.debug(
            "Setting power state for device %s (ID: %s) to %s",
            device.name,
            device.id,
            "on" if power else "off",
        )

        try:
            payload = {
                "power": "on" if power else "off",
                "uniqueId": device.id,
                "acknowledged": acknowledged,
                "retries": retries,
                "timeout_ms": timeout_ms,
            }

            response = await self._put(
                Endpoints.DEVICE_POWER.value,
                json=payload,
                timeout=timeout_ms / 1000 + 1,  # Convert to seconds and add buffer
            )

            # Update device timestamp
            device.update_timestamp()

            logger.debug(
                "Successfully set power state to %s for device %s",
                "on" if power else "off",
                device.name,
            )

        except HafeleAPIError as e:
            logger.error(
                "Failed to set power state for device %s (ID: %s)."
                " Status: %s, Error: %s",
                device.name,
                device.id,
                e.status_code,
                e.error_code,
            )
            raise

    async def power_on(
        self,
        device: Device,
        acknowledged: bool = True,
        retries: int = 0,
        timeout_ms: int = 10000,
    ) -> None:
        """
        Turn on a device.

        Convenience method that calls set_power with power=True.

        Args:
            device: Device instance to turn on
            acknowledged: Whether to wait for acknowledgment (default: True)
            retries: Number of mesh-level retries (default: 0)
            timeout_ms: Mesh operation timeout in milliseconds (default: 10000)

        """
        await self.set_power(device, True, acknowledged, retries, timeout_ms)

    async def power_off(
        self,
        device: Device,
        acknowledged: bool = True,
        retries: int = 0,
        timeout_ms: int = 10000,
    ) -> None:
        """
        Turn off a device.

        Convenience method that calls set_power with power=False.

        Args:
            device: Device instance to turn off
            acknowledged: Whether to wait for acknowledgment (default: True)
            retries: Number of mesh-level retries (default: 0)
            timeout_ms: Mesh operation timeout in milliseconds (default: 10000)

        """
        await self.set_power(device, False, acknowledged, retries, timeout_ms)

    async def set_lightness(
        self,
        device: Device,
        lightness: float,
        acknowledged: bool = True,
        retries: int = 0,
        timeout_ms: int = 10000,
    ) -> None:
        """
        Set the brightness of a light device.

        Args:
            device: Device instance to control
            lightness: Brightness value between 0 and 1 (0 = off, 1 = full brightness)
            acknowledged: Whether to wait for acknowledgment (default: True)
            retries: Number of mesh-level retries (default: 0)
            timeout_ms: Mesh operation timeout in milliseconds (default: 10000)

        Raises:
            HafeleAPIError: If the API request fails
            ValidationError: If device data is invalid or device is not a light
            ValueError: If lightness is out of range

        """
        if not device.is_light:
            raise ValidationError(f"Device {device.name} is not a light")

        if not 0 <= lightness <= 1:
            raise ValueError(f"Lightness must be between 0 and 1, got {lightness}")

        logger.debug(
            "Setting lightness for device %s (ID: %s) to %.2f",
            device.name,
            device.id,
            lightness,
        )

        try:
            payload = {
                "lightness": lightness,
                "uniqueId": device.id,
                "acknowledged": acknowledged,
                "retries": retries,
                "timeout_ms": timeout_ms,
            }

            response = await self._put(
                Endpoints.DEVICE_LIGHTNESS.value,
                json=payload,
                timeout=timeout_ms / 1000 + 1,
            )

            response_data = await response.json()
            if not response_data.get("success", False):
                error = response_data.get("error", "UNKNOWN_ERROR")
                raise HafeleAPIError(
                    message=f"Failed to set lightness: {error}", error_code=error
                )

            device.update_timestamp()

            logger.debug(
                "Successfully set lightness to %.2f for device %s",
                lightness,
                device.name,
            )

        except HafeleAPIError as e:
            logger.error(
                "Failed to set lightness for device %s (ID: %s). Status: %s, Error: %s",
                device.name,
                device.id,
                e.status_code,
                e.error_code,
            )
            raise

    async def set_temperature(
        self,
        device: Device,
        temperature: int,
        acknowledged: bool = True,
        retries: int = 0,
        timeout_ms: int = 10000,
    ) -> None:
        """
        Set the color temperature of a light device.

        Args:
            device: Device instance to control
            temperature: Color temperature value (0-65535)
            acknowledged: Whether to wait for acknowledgment (default: True)
            retries: Number of mesh-level retries (default: 0)
            timeout_ms: Mesh operation timeout in milliseconds (default: 10000)

        Raises:
            HafeleAPIError: If the API request fails
            ValidationError: If device data is invalid or device is not a light
            ValueError: If temperature is out of range

        """
        if not device.supports_color_temp:
            raise ValidationError(
                f"Device {device.name} does not support color temperature"
            )

        if not 0 <= temperature <= 65535:
            raise ValueError(
                f"Temperature must be between 0 and 65535, got {temperature}"
            )

        logger.debug(
            "Setting temperature for device %s (ID: %s) to %d",
            device.name,
            device.id,
            temperature,
        )

        try:
            payload = {
                "temperature": temperature,
                "uniqueId": device.id,
                "acknowledged": acknowledged,
                "retries": retries,
                "timeout_ms": timeout_ms,
            }

            response = await self._put(
                Endpoints.DEVICE_TEMPERATURE.value,
                json=payload,
                timeout=timeout_ms / 1000 + 1,
            )

            response_data = await response.json()
            if not response_data.get("success", False):
                error = response_data.get("error", "UNKNOWN_ERROR")
                raise HafeleAPIError(
                    message=f"Failed to set temperature: {error}", error_code=error
                )

            device.update_timestamp()

            logger.debug(
                "Successfully set temperature to %d for device %s",
                temperature,
                device.name,
            )

        except HafeleAPIError as e:
            logger.error(
                "Failed to set temperature for device %s (ID: %s)."
                " Status: %s, Error: %s",
                device.name,
                device.id,
                e.status_code,
                e.error_code,
            )
            raise

    async def set_hsl(
        self,
        device: Device,
        hue: float,
        saturation: float,
        lightness: float = None,
        acknowledged: bool = True,
        retries: int = 0,
        timeout_ms: int = 10000,
    ) -> None:
        """
        Set the HSL values of a light device.

        Args:
            device: Device instance to control
            hue: Hue value (0-360)
            saturation: Saturation value (0-1)
            lightness: Lightness value (0-1)
            acknowledged: Whether to wait for acknowledgment (default: True)
            retries: Number of mesh-level retries (default: 0)
            timeout_ms: Mesh operation timeout in milliseconds (default: 10000)

        Raises:
            HafeleAPIError: If the API request fails
            ValidationError: If device data is invalid or device is not a light
            ValueError: If HSL values are out of range

        """
        if not device.supports_hsl:
            raise ValidationError(f"Device {device.name} does not support HSL color")

        # Validate HSL values
        if not 0 <= hue <= 360:
            raise ValueError(f"Hue must be between 0 and 360, got {hue}")
        if not 0 <= saturation <= 1:
            raise ValueError(f"Saturation must be between 0 and 1, got {saturation}")
        if not 0 <= lightness <= 1:
            raise ValueError(f"Lightness must be between 0 and 1, got {lightness}")

        logger.debug(
            "Setting HSL for device %s (ID: %s) to H:%.1f S:%.2f L:%.2f",
            device.name,
            device.id,
            hue,
            saturation,
            lightness,
        )

        try:
            payload = {
                "hue": hue,
                "saturation": saturation,
                "lightness": lightness,
                "uniqueId": device.id,
                "acknowledged": acknowledged,
                "retries": retries,
                "timeout_ms": timeout_ms,
            }

            response = await self._put(
                Endpoints.DEVICE_HSL.value,
                json=payload,
                timeout=timeout_ms / 1000 + 1,
            )

            response_data = await response.json()
            if not response_data.get("success", False):
                error = response_data.get("error", "UNKNOWN_ERROR")
                raise HafeleAPIError(
                    message=f"Failed to set HSL values: {error}", error_code=error
                )

            device.update_timestamp()

            logger.debug(
                "Successfully set HSL values for device %s",
                device.name,
            )

        except HafeleAPIError as e:
            logger.error(
                "Failed to set HSL for device %s (ID: %s). Status: %s, Error: %s",
                device.name,
                device.id,
                e.status_code,
                e.error_code,
            )
            raise

    @staticmethod
    def brightness_to_api(brightness: int) -> float:
        """
        Convert 0-255 brightness value to 0-1 API scale.

        Args:
            brightness: Brightness value (0-255)

        Returns:
            Float value between 0-1 for API

        Raises:
            ValueError: If brightness is out of range

        """
        if not 0 <= brightness <= 255:
            raise ValueError(f"Brightness must be between 0 and 255, got {brightness}")
        return brightness / 255.0

    @staticmethod
    def api_to_brightness(api_value: float) -> int:
        """
        Convert 0-1 API value to 0-255 brightness scale.

        Args:
            api_value: API lightness value (0-1)

        Returns:
            Integer brightness value (0-255)

        Raises:
            ValueError: If api_value is out of range

        """
        if not 0 <= api_value <= 1:
            raise ValueError(f"API value must be between 0 and 1, got {api_value}")
        return round(api_value * 255)

    @staticmethod
    def mesh_to_brightness(mesh_value: int) -> int:
        """
        Convert 0-65535 mesh value to 0-255 brightness scale.

        Args:
            mesh_value: Mesh lightness value (0-65535)

        Returns:
            Integer brightness value (0-255)

        Raises:
            ValueError: If mesh_value is out of range

        """
        if not 0 <= mesh_value <= 65535:
            raise ValueError(
                f"Mesh value must be between 0 and 65535, got {mesh_value}"
            )
        return round(mesh_value / 65535 * 255)

    @staticmethod
    def brightness_to_mesh(brightness: int) -> int:
        """
        Convert 0-255 brightness value to 0-65535 mesh scale.

        Args:
            brightness: Brightness value (0-255)

        Returns:
            Integer mesh value (0-65535)

        Raises:
            ValueError: If brightness is out of range

        """
        if not 0 <= brightness <= 255:
            raise ValueError(f"Brightness must be between 0 and 255, got {brightness}")
        return round(brightness / 255 * 65535)

    @staticmethod
    def api_to_mesh(api_value: float) -> int:
        """
        Convert 0-1 API value to 0-65535 mesh scale.

        Args:
            api_value: API lightness value (0-1)

        Returns:
            Integer mesh value (0-65535)

        Raises:
            ValueError: If api_value is out of range

        """
        if not 0 <= api_value <= 1:
            raise ValueError(f"API value must be between 0 and 1, got {api_value}")
        return round(api_value * 65535)

    @staticmethod
    def mesh_to_api(mesh_value: int) -> float:
        """
        Convert 0-65535 mesh value to 0-1 API scale.

        Args:
            mesh_value: Mesh lightness value (0-65535)

        Returns:
            Float value between 0-1 for API

        Raises:
            ValueError: If mesh_value is out of range

        """
        if not 0 <= mesh_value <= 65535:
            raise ValueError(
                f"Mesh value must be between 0 and 65535, got {mesh_value}"
            )
        return mesh_value / 65535

    @staticmethod
    def mesh_to_mireds(mesh_value: int) -> int:
        """
        Convert 0-65535 mesh value to mireds (color temperature).

        Args:
            mesh_value: Mesh temperature value (0-65535)

        Returns:
            Integer mireds value

        Raises:
            ValueError: If mesh_value is out of range

        """
        if not 0 <= mesh_value <= 65535:
            raise ValueError(
                f"Mesh value must be between 0 and 65535, got {mesh_value}"
            )
        # Convert to mireds (typical range 153-500)
        # You may need to adjust these values based on your device's capabilities
        return round(153 + (mesh_value / 65535) * (500 - 153))

    @staticmethod
    def mireds_to_mesh(mireds: int) -> int:
        """
        Convert mireds to 0-65535 mesh scale.

        Args:
            mireds: Color temperature in mireds (typically 153-500)

        Returns:
            Integer mesh value (0-65535)

        Raises:
            ValueError: If mireds is out of range

        """
        if not 153 <= mireds <= 500:
            raise ValueError(f"Mireds must be between 153 and 500, got {mireds}")
        # Convert from mireds to mesh value
        return round(((mireds - 153) / (500 - 153)) * 65535)
