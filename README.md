# Häfele Connect Mesh Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/default) ![GitHub Release](https://img.shields.io/github/v/release/QNimbus/haefele-connect-mesh) ![License](https://img.shields.io/github/license/QNimbus/haefele-connect-mesh) ![HA minimum version](https://img.shields.io/badge/HA%20minimum-2024.1.0-blue?logo=home-assistant)

[![Validate](https://github.com/QNimbus/haefele-connect-mesh/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/QNimbus/haefele-connect-mesh/actions/workflows/validate.yml)
[![Validate with hassfest](https://github.com/QNimbus/haefele-connect-mesh/actions/workflows/hassfest.yml/badge.svg?branch=main)](https://github.com/QNimbus/haefele-connect-mesh/actions/workflows/hassfest.yml)

![Häfele](./custom_components/haefele_connect_mesh/logo/icon.png)

A Home Assistant custom integration for Häfele Connect Mesh devices. This integration allows you to control Häfele smart devices through Home Assistant.

## Update (03-2025): Local MQTT Mode

The integration now supports a **local MQTT mode** as an alternative to cloud polling. Instead of routing commands through the Häfele cloud API, local mode communicates directly with your Connect Mesh Gateway over MQTT — giving you faster response times, no dependency on cloud availability, and full local control.

You can choose between two MQTT connection options:

- **Use HA's built-in MQTT integration** — if you already have the Home Assistant MQTT integration configured, the Häfele integration can piggyback on that connection.
- **Connect directly to a broker** — point the integration at any MQTT broker (hostname, port, and optional credentials) that your gateway publishes to.

Once set up, devices are discovered automatically from the gateway's MQTT topics. Device states are kept up to date via push notifications from the gateway — physical toggles (wall switches, remotes) are reflected in Home Assistant instantly without any polling.

## Update (04-12-2024) 🎊

I'm excited to share some great news regarding the Häfele Connect Mesh integration! Recently, I had the opportunity to connect with Häfele, and I'm delighted to report that they are not only aware of this project but are also highly supportive of Open Source Initiative (OSI) principles and open-source development as a whole. Häfele recognizes the importance of community-driven platforms like Home Assistant and is eager to see seamless integrations that benefit both their customers and the broader open-source community.

To support the development and testing of this integration, Häfele has generously provided me with a selection of their hardware. This will enable me to expand the capabilities of the Häfele Home Assistant integration and ensure broader compatibility with their product lineup.

You can expect to see more features, enhanced stability, and support for additional Häfele devices in the coming months as I put this hardware to work. Stay tuned for updates!

## Supported Devices

Currently, this integration has been tested with:
- Häfele LED lights (dimmable)
- Power socket (Häfele, LEDVance or Jung)

While the integration includes support for color temperature and RGB/HSL capable lights, as well as other device types (switches, sensors, etc.), these features are currently **untested** as I don't have access to these device types.

## Prerequisites

- A working Häfele Connect Mesh setup ([Häfele Connect Mesh Gateway](https://www.hafele.nl/nl/product/gateway-haefele-connect-mesh/85000074))
- Home Assistant 2024.1.0 or newer

**Cloud mode** additionally requires:
- A Häfele Connect Mesh API token — sign up at [Connect Mesh Cloud](https://cloud.connect-mesh.io/developer) and generate a token

**Local MQTT mode** additionally requires:
- An MQTT broker accessible from Home Assistant (e.g. the [Mosquitto broker add-on](https://github.com/home-assistant/addons/tree/master/mosquitto)) that your Connect Mesh Gateway publishes to

## Installation

### Using HACS (Recommended)

1. Make sure you have [HACS](https://hacs.xyz/) installed
2. Go to **HACS → Integrations** and search for **Häfele Connect Mesh**
3. Click **Download**
4. Restart Home Assistant

### Manual Installation

1. Copy the `haefele_connect_mesh` folder to your `custom_components` folder
2. Restart Home Assistant

## Configuration

1. Go to **Settings → Devices & Services**
2. Click **Add Integration** and search for **Häfele Connect Mesh**
3. Choose your connection type:

**Cloud mode:**
1. Enter your API token (sign up at [Connect Mesh Cloud](https://cloud.connect-mesh.io/developer) to generate one)
2. Select the network you want to add

**Local MQTT mode:**
1. Choose whether to use HA's built-in MQTT integration or connect directly to a broker
2. Enter the topic prefix your Connect Mesh Gateway publishes to (default: `hafele`)
3. If connecting directly to a broker, enter the broker hostname, port, and optional credentials
4. Optionally enable group entity creation (for tactile remote / wall switch support)

## Features

- Two connection modes: **cloud polling** (via Häfele cloud API) or **local MQTT** (direct gateway communication)
- Automatic device discovery from the gateway
- Automatic periodic refresh of device names
- Support for turning lights on/off and dimming
- Support for color temperature (untested)
- Support for RGB/HSL colors (untested)
- **Local MQTT mode:**
  - Push-based state updates via BLE Mesh rawMessage — physical toggles (wall switches, remotes) reflected instantly
  - Group light entities — tactile wall remotes that control a group of lights are represented as a single HA entity
  - No cloud dependency

## Limitations

- Color temperature and RGB/HSL features are untested
- Switch-type devices (non-light nodes) are discovered but not exposed as HA entities
- In local MQTT mode, device discovery depends on the Connect Mesh Gateway publishing to the configured topic prefix

## Contributing

Feel free to contribute to this project if you have access to other Häfele device types and can help test and improve the integration.

## Issues

If you find any bugs or have feature requests, please create an issue in this repository.

## Removal

1. Go to **Settings → Devices & Services**
2. Find the **Häfele Connect Mesh** integration card
3. Click the three-dot menu and select **Delete**
4. Restart Home Assistant if prompted

If installed via HACS, you can also uninstall it from **HACS → Integrations** after deleting the integration.

## License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

## Disclaimer

This integration is not officially affiliated with or endorsed by Häfele. Use at your own risk.
