"""Constants for the Häfele Connect Mesh integration."""

NAME = "Häfele Connect Mesh"
DOMAIN = "haefele_connect_mesh"
VERSION = "0.1.0"

# Configuration
CONF_NETWORK_ID = "network_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_NEW_DEVICES_CHECK_INTERVAL = "new_devices_check_interval"
CONF_DEVICE_DETAILS_UPDATE_INTERVAL = "device_details_update_interval"
CONF_CONNECTION_TYPE = "connection_type"
CONNECTION_TYPE_MQTT = "mqtt"
CONNECTION_TYPE_CLOUD = "cloud"
CONF_MQTT_TOPIC_PREFIX = "topic_prefix"
DEFAULT_MQTT_TOPIC_PREFIX = "hafele"
CONF_MQTT_USE_HA = "use_ha_mqtt"
CONF_MQTT_BROKER = "broker"
CONF_MQTT_PORT = "port"
CONF_MQTT_USERNAME = "username"
CONF_MQTT_PASSWORD = "password"
DEFAULT_MQTT_PORT = 1883
# Device Capabilities

BRIGHTNESS_SCALE_PERCENTAGE = (1, 100)  # Percentage
BRIGHTNESS_SCALE_HA = (1, 255)  # Home Assistant brightness scale
BRIGHTNESS_SCALE_MESH = (1, 65535)  # Mesh brightness scale
MIN_KELVIN = 2000  # Minimum color temperature in Kelvin
MAX_KELVIN = 6500  # Maximum color temperature in Kelvin
MIN_MIREDS = 153  # Minimum color temperature in mireds
MAX_MIREDS = 500  # Maximum color temperature in mireds

DEFAULT_SCAN_INTERVAL = 30  # Default scan interval in seconds
DEFAULT_NEW_DEVICES_CHECK_INTERVAL = 15  # Default check interval in minutes
DEFAULT_DEVICE_DETAILS_UPDATE_INTERVAL = 5  # Default device details update interval in minutes
