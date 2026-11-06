# Oasira Business Integration

This directory contains the Home Assistant custom integration for Oasira Business.

The integration provides local Home Assistant entities for security, presence,
doors, windows, environmental monitoring, lights, covers, and switches, plus
area and label management services, motion and security sensor groups, and
optional Oasira Care API streaming and backup support.

## Functional Scope

### Area and Entity Management

* `update_entity` service to assign an entity to an area (administrator only)
* `add_label_to_entity` service to add a label to an entity (administrator only)
* Integration startup label bootstrap for Favorite and NotForSecurityMonitoring
* `set_in_bed_state` service to update the in-bed binary sensor for an area

### Sensors and Groups

* Motion and security sensor groups created at startup
* Presence, door, window, smoke, moisture, and carbon monoxide group sensors
* Environmental sensors for illuminance, temperature, and humidity

### Care API Streaming and Backups

* Optional streaming of alerts and telemetry to an Oasira Care API when a Care API URL and facility ingest key are configured
* Oasira Care appears as a backup location in Home Assistant's native backup feature once enrolled or once the Care API options are set

### Automation Assets and UX

* Automation and script blueprints under `blueprints/` covering lighting, climate, calendars, appliances, pool management, presence, and offline-device reports
* Theme under `themes/` (`Oasira.yaml`)
* Websocket subscription (`oasira_b2b_updated`) registered during setup for custom Lovelace cards; no frontend JS assets are shipped with the integration

## Home Assistant Platforms

The integration forwards setup to these platforms:

* `switch`
* `binary_sensor`
* `sensor`
* `cover`
* `light`
* `stt` — account-based entries only; enrolled hub entries omit this platform

## Service Reference

Primary service definitions are documented in `services.yaml` in this folder.

The `oasira_b2b` domain registers:

* `update_entity`
* `add_label_to_entity`
* `set_in_bed_state`

For backward compatibility, `update_entity` and `add_label_to_entity` are also registered under the legacy `oasira` domain.

## Installation

### HACS

1. Add this repository as a custom repository in HACS
2. Install Oasira Business
3. Restart Home Assistant
4. Add the integration from Settings > Devices and Services

### Manual

1. Copy this folder to custom_components/oasira_b2b
2. Restart Home Assistant
3. Add Oasira Business from Settings > Devices and Services

## Requirements

* Home Assistant with config flow support
* Recorder integration enabled
* Network access to Oasira cloud endpoints

Python dependencies are declared in `manifest.json` and installed automatically by Home Assistant.

## Support

* Issues: https://github.com/EffortlessHome/Oasira_b2b/issues
* Website: https://www.oasira.ai/
