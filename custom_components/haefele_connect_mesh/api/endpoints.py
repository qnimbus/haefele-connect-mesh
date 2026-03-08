"""
Häfele Connect Mesh API endpoint definitions.

This module contains all API endpoint URLs and related constants used
by the API client to interact with the Häfele Connect Mesh API.
"""

from enum import Enum

# Base API URL
BASE_URL = "https://cloud.connect-mesh.io/api/core"


class Endpoints(str, Enum):
    """API endpoint paths."""

    # Networks
    NETWORKS = "/networks"
    NETWORK_DETAIL = "/networks/{id}"

    # Devices
    DEVICES = "/devices"
    DEVICE_DETAIL = "/devices/{id}"
    DEVICE_STATUS = "/devices/{id}/status"
    DEVICE_POWER = "/devices/power"
    DEVICE_LIGHTNESS = "/devices/lightness"
    DEVICE_TEMPERATURE = "/devices/temperature"
    DEVICE_HSL = "/devices/hsl"

    # Groups
    GROUPS = "/groups"
    GROUP_POWER = "/groups/power"
    GROUP_LIGHTNESS = "/groups/lightness"

    # Scenes
    SCENES = "/scenes"
    SCENE_RECALL = "/scenes/recall/{scene_id}"

    # Gateways
    GATEWAYS = "/gateways"
    GATEWAY_PING = "/gateway/ping/{id}"
