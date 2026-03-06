"""Config flow for Häfele Connect Mesh integration."""

from __future__ import annotations

import logging
from typing import Any, Mapping

import voluptuous as vol
import aiohttp

from homeassistant import config_entries
from homeassistant.const import CONF_API_TOKEN
from homeassistant.data_entry_flow import FlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    DOMAIN,
    CONF_NETWORK_ID,
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_MQTT,
    CONNECTION_TYPE_CLOUD,
    CONF_MQTT_TOPIC_PREFIX,
    DEFAULT_MQTT_TOPIC_PREFIX,
    CONF_MQTT_USE_HA,
    CONF_MQTT_BROKER,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    CONF_MQTT_PASSWORD,
    DEFAULT_MQTT_PORT,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    CONF_DEVICE_DETAILS_UPDATE_INTERVAL,
    DEFAULT_DEVICE_DETAILS_UPDATE_INTERVAL,
    CONF_NEW_DEVICES_CHECK_INTERVAL,
    DEFAULT_NEW_DEVICES_CHECK_INTERVAL,
)
from .api.client import HafeleClient
from .exceptions import HafeleAPIError

_LOGGER = logging.getLogger(__name__)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Häfele Connect Mesh."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return the options flow handler."""
        return OptionsFlowHandler(config_entry)

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._api_token: str | None = None
        self._networks: list[dict] | None = None
        self._mqtt_topic_prefix: str | None = None
        self._reauth_entry = None

    # ------------------------------------------------------------------
    # Step 1: choose connection type
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask whether to use local MQTT or cloud API."""
        if user_input is not None:
            connection_type = user_input[CONF_CONNECTION_TYPE]
            if connection_type == CONNECTION_TYPE_MQTT:
                return await self.async_step_mqtt_setup()
            return await self.async_step_cloud_credentials()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CONNECTION_TYPE, default=CONNECTION_TYPE_MQTT
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[CONNECTION_TYPE_MQTT, CONNECTION_TYPE_CLOUD],
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_CONNECTION_TYPE,
                        )
                    ),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Step 2a: MQTT setup
    # ------------------------------------------------------------------

    async def async_step_mqtt_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure MQTT broker source and topic prefix."""
        errors: dict[str, str] = {}
        ha_mqtt_available = "mqtt" in self.hass.config.components

        if user_input is not None:
            use_ha = user_input[CONF_MQTT_USE_HA]
            self._mqtt_topic_prefix = user_input[CONF_MQTT_TOPIC_PREFIX]

            if use_ha:
                if not ha_mqtt_available:
                    errors["base"] = "mqtt_not_configured"
                else:
                    await self.async_set_unique_id(f"mqtt_{self._mqtt_topic_prefix}")
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="Häfele Connect Mesh (Local)",
                        data={
                            CONF_CONNECTION_TYPE: CONNECTION_TYPE_MQTT,
                            CONF_MQTT_TOPIC_PREFIX: self._mqtt_topic_prefix,
                            CONF_MQTT_USE_HA: True,
                        },
                    )
            else:
                return await self.async_step_mqtt_broker()

        return self.async_show_form(
            step_id="mqtt_setup",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_MQTT_USE_HA, default=ha_mqtt_available
                    ): BooleanSelector(),
                    vol.Required(
                        CONF_MQTT_TOPIC_PREFIX, default=DEFAULT_MQTT_TOPIC_PREFIX
                    ): str,
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2a (continued): custom MQTT broker credentials
    # ------------------------------------------------------------------

    async def async_step_mqtt_broker(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure custom MQTT broker connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(f"mqtt_{self._mqtt_topic_prefix}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Häfele Connect Mesh (Local)",
                data={
                    CONF_CONNECTION_TYPE: CONNECTION_TYPE_MQTT,
                    CONF_MQTT_TOPIC_PREFIX: self._mqtt_topic_prefix,
                    CONF_MQTT_USE_HA: False,
                    CONF_MQTT_BROKER: user_input[CONF_MQTT_BROKER],
                    CONF_MQTT_PORT: user_input[CONF_MQTT_PORT],
                    CONF_MQTT_USERNAME: user_input.get(CONF_MQTT_USERNAME, ""),
                    CONF_MQTT_PASSWORD: user_input.get(CONF_MQTT_PASSWORD, ""),
                },
            )

        return self.async_show_form(
            step_id="mqtt_broker",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MQTT_BROKER): str,
                    vol.Required(
                        CONF_MQTT_PORT, default=DEFAULT_MQTT_PORT
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1, max=65535, mode=NumberSelectorMode.BOX
                        )
                    ),
                    vol.Optional(CONF_MQTT_USERNAME): TextSelector(
                        TextSelectorConfig(autocomplete="username")
                    ),
                    vol.Optional(CONF_MQTT_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2b: cloud credentials (formerly async_step_user)
    # ------------------------------------------------------------------

    async def async_step_cloud_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle cloud API token entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            api_token = user_input[CONF_API_TOKEN]
            valid, error = await self._validate_api_token(api_token)

            if valid:
                self._api_token = api_token
                return await self.async_step_network()

            errors["base"] = error

        return self.async_show_form(
            step_id="cloud_credentials",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_TOKEN): str,
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 3 (cloud only): network selection
    # ------------------------------------------------------------------

    async def async_step_network(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle network selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            network_id = user_input[CONF_NETWORK_ID]
            selected_network = next(
                (net for net in self._networks if net["id"] == network_id), None
            )

            if selected_network:
                await self.async_set_unique_id(network_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=selected_network["name"],
                    data={
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_CLOUD,
                        CONF_API_TOKEN: self._api_token,
                        CONF_NETWORK_ID: network_id,
                    },
                )

            errors["base"] = "network_not_found"

        network_options = {
            net["id"]: f"{net['name']} ({net['device_count']})"
            for net in self._networks
        }

        placeholders = {
            "device_count": str(sum(net["device_count"] for net in self._networks)),
        }

        return self.async_show_form(
            step_id="network",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NETWORK_ID): vol.In(network_options),
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    # ------------------------------------------------------------------
    # Reauth
    # ------------------------------------------------------------------

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Handle reauthorization request."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauthorization confirmation."""
        errors = {}

        if user_input is not None:
            api_token = user_input[CONF_API_TOKEN]
            valid, error = await self._validate_api_token(api_token)

            if valid:
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={**self._reauth_entry.data, CONF_API_TOKEN: api_token},
                )
                await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_API_TOKEN): str,
            }),
            errors=errors,
            description_placeholders={
                "error_detail": errors.get("base", "")
            },
        )

    # ------------------------------------------------------------------
    # Migration
    # ------------------------------------------------------------------

    async def async_migrate_entry(self, config_entry: config_entries.ConfigEntry) -> bool:
        """Migrate old entry."""
        _LOGGER.debug("Migrating from version %s", config_entry.version)

        if config_entry.version == 1:
            # No migration needed yet
            return True

        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _validate_api_token(self, api_token: str) -> tuple[bool, str | None]:
        """Validate the API token by fetching networks."""
        session = async_get_clientsession(self.hass)
        client = HafeleClient(api_token, session, timeout=6)

        try:
            networks = await client.get_networks()
            if not networks:
                return False, "no_networks_found"

            self._networks = []
            for network in networks:
                devices = await client.get_devices_for_network(network.id)
                self._networks.append(
                    {
                        "id": network.id,
                        "name": network.name,
                        "device_count": len(devices),
                    }
                )
            return True, None
        except HafeleAPIError as err:
            _LOGGER.error("Failed to connect to Häfele API: %s", err)
            if "401" in str(err):
                return False, "invalid_auth"
            return False, "cannot_connect"
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected error occurred: %s", err)
            return False, "unknown"


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for Häfele Connect Mesh."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Route to the appropriate options step based on connection type."""
        if self._entry.data.get(CONF_CONNECTION_TYPE) == CONNECTION_TYPE_CLOUD:
            return await self.async_step_cloud_options(user_input)
        # MQTT is pure push — no options to configure
        return self.async_create_entry(title="", data={})

    async def async_step_cloud_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage cloud polling intervals."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_DEVICE_DETAILS_UPDATE_INTERVAL: int(
                        user_input[CONF_DEVICE_DETAILS_UPDATE_INTERVAL]
                    ),
                    CONF_NEW_DEVICES_CHECK_INTERVAL: int(
                        user_input[CONF_NEW_DEVICES_CHECK_INTERVAL]
                    ),
                },
            )

        current_scan = self._entry.options.get(
            CONF_SCAN_INTERVAL,
            self._entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        current_details = self._entry.options.get(
            CONF_DEVICE_DETAILS_UPDATE_INTERVAL,
            self._entry.data.get(
                CONF_DEVICE_DETAILS_UPDATE_INTERVAL,
                DEFAULT_DEVICE_DETAILS_UPDATE_INTERVAL,
            ),
        )
        current_new_devices = self._entry.options.get(
            CONF_NEW_DEVICES_CHECK_INTERVAL,
            self._entry.data.get(
                CONF_NEW_DEVICES_CHECK_INTERVAL, DEFAULT_NEW_DEVICES_CHECK_INTERVAL
            ),
        )

        return self.async_show_form(
            step_id="cloud_options",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=current_scan
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=10,
                            max=300,
                            step=5,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="s",
                        )
                    ),
                    vol.Required(
                        CONF_DEVICE_DETAILS_UPDATE_INTERVAL, default=current_details
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=60,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="min",
                        )
                    ),
                    vol.Required(
                        CONF_NEW_DEVICES_CHECK_INTERVAL, default=current_new_devices
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=60,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="min",
                        )
                    ),
                }
            ),
        )

