# Green Mountain Grill Cloud Integration for Home Assistant

A custom [Home Assistant](https://www.home-assistant.io/) integration that monitors [Green Mountain Grills](https://greenmountaingrills.com/) (GMG) via the GMG cloud API -- the same API used by the official **GMG Prime** mobile app.

## Features

- **Grill temperature** monitoring (current and target)
- **Food probe temperatures** (Probe 1 and Probe 2, current and target)
- **Grill status** -- off, grilling, smoking, fan mode
- **Low pellets alert** -- binary sensor that triggers when pellets are low
- **Warning sensor** -- low pellets, fan disconnect, ignitor disconnect, auger disconnect
- **Fire state** sensor with ignition progress
- **Cook profile** status -- active, paused, or none (with remaining time)
- **Firmware version** and **last cloud update** timestamp
- **Climate entity** for grill temperature display and (future) control

## Prerequisites

- A Green Mountain Grill with Wi-Fi connectivity in **Server Mode** (cloud-connected)
- A GMG Prime app account (email + password)
- Home Assistant 2024.1 or newer

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click the three dots in the top right corner and select **Custom repositories**
3. Add `https://github.com/c0ryd/ha-gmg-cloud` with category **Integration**
4. Click **Install**
5. Restart Home Assistant

### Manual Installation

1. Download the latest release from [GitHub](https://github.com/c0ryd/ha-gmg-cloud/releases)
2. Copy the `custom_components/gmg_cloud` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** > **Devices & Services** > **Add Integration**
2. Search for **Green Mountain Grill Cloud**
3. Enter your GMG Prime app credentials (email and password)
4. The integration will discover your grill(s) automatically

## Entities

### Climate

| Entity | Description |
|--------|-------------|
| GMG Grill | Shows current grill temp and target temp. Displays HEAT when grilling/smoking, OFF otherwise. |

### Sensors

| Entity | Description |
|--------|-------------|
| Food Probe 1 | Food probe 1 temperature |
| Food Probe 2 | Food probe 2 temperature |
| Target Grill Temp | Set grill temperature (blank when not set) |
| Target Probe 1 Temp | Target temperature for food probe 1 |
| Target Probe 2 Temp | Target temperature for food probe 2 |
| Status | Grill operating state: off, grilling, smoking, fan_mode, offline |
| Warning | Active warning: none, low_pellets, fan_disconnect, ignitor_disconnect, auger_disconnect |
| Fire State | Fire/ignitor state value with ignition progress |
| Cook Profile | Cook profile status: none, active, paused (remaining time in attributes) |
| Firmware Version | Current firmware version (diagnostic) |
| Last Updated | Last cloud update timestamp (diagnostic) |

### Binary Sensors

| Entity | Description |
|--------|-------------|
| Low Pellets | ON when pellets are low, OFF otherwise. Device class: problem. |

## Temperature Units

The grill reports temperatures in Fahrenheit. Home Assistant will automatically convert to your configured unit system. To display in Fahrenheit while keeping the rest of your system in Celsius:

1. Click on any temperature entity
2. Click the gear icon (settings)
3. Change **Unit of measurement** to °F

## How It Works

This integration authenticates with AWS Cognito (the same auth used by the GMG Prime app) and polls the GMG cloud REST API every 30 seconds for grill state data. The protocol was reverse engineered from the GMG Prime Android app.

### API Endpoints Used

- `GET /grill` -- Discover grills on the account
- `GET /grill/{connectionType}|{grillId}/state` -- Poll grill state (temperatures, warnings, profile status, etc.)

## Current Limitations

- **Read-only** -- Command sending (set temperature, power on/off) is not yet implemented. The command protocol has been reverse engineered and will be added in a future release.
- **Cloud-only** -- Requires internet connectivity. Local/Bluetooth control is not supported.
- **Polling-based** -- Updates every 30 seconds. Not real-time.

## Roadmap

- [ ] Command support (set grill temp, set probe temps, power on/off)
- [ ] Configurable polling interval
- [ ] Cook profile management
- [ ] Temperature alert automations

## Contributing

Contributions are welcome! If you have a GMG grill and want to help test or develop, please open an issue or PR.

## Disclaimer

This integration is not affiliated with, endorsed by, or connected to Green Mountain Grills. Use at your own risk. The authors are not responsible for any damage to your grill or food.

## License

[MIT](LICENSE)
