# Oasira Business

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-1.2.6-blue.svg)](https://github.com/EffortlessHome/Oasira_B2B)

Oasira Business connects a Home Assistant hub to an Oasira Care facility and
provides local entities, automations, services, and optional Care API streaming.

## Available functionality

- Enroll one Home Assistant hub per installation in an Oasira Care facility.
- Provide Home Assistant entities for security, presence, doors, windows,
  environmental monitoring, lights, covers, switches, and speech-to-text.
  Speech-to-text is available for account-based entries; enrolled hub entries
  omit that platform.
- Create motion and security sensor groups at startup and maintain the
  integration's standard labels.
- Use the included automation blueprints for security, presence, lighting,
  climate, cameras and AI-assisted notifications, calendars, appliances,
  offline-device reports, and other household workflows.
- Use optional Care API streaming when a Care API URL and facility ingest key
  are configured.
- Use the included frontend panels to assign entities to areas and labels, view
  Matter Hub bridge status and pairing details, and access Home Assistant
  account controls.

The integration is cloud-connected (`cloud_polling`). Home Assistant
automations and entity management run in Home Assistant; API-backed functions
and optional Care streaming require network access to Oasira Care.

## Installation

### HACS

1. In HACS, add this repository as a custom repository.
2. Find and install **Oasira Business**.
3. Restart Home Assistant.
4. Add **Oasira Business** from **Settings > Devices & services**.

### Manual

1. Copy `custom_components/oasira_b2b` into your Home Assistant
   `custom_components` directory.
2. Restart Home Assistant.
3. Add **Oasira Business** from **Settings > Devices & services**.

## Enroll a hub

The integration supports one configured hub per Home Assistant instance. In
the integration setup form, provide:

- **API URL**: the Oasira Care API base URL using HTTP or HTTPS, with or without a trailing `/v1`.
- **Enrollment code**: a one-time code issued from Oasira Care's facility hub
  provisioning workflow.
- **Hub name**: optional; defaults to the Home Assistant location name.

Enrollment associates the hub with the facility and provisions a hub API key.
If the key is revoked or lost, re-enroll the hub with a new code from the same
facility.

Account-based legacy entries can also configure an optional Care API URL and
facility ingest key in the integration options. Configure both values or leave
both blank.

## Services

The `oasira_b2b` domain registers these services:

| Service | Purpose |
| --- | --- |
| `create_event` | Send an event for an eligible entity associated with an active Oasira alarm. |
| `create_alert` | Create or update an alert with a type, description, and status. |
| `update_entity` | Assign an entity to an area; used by the area panel. Administrator only. |
| `add_label_to_entity` | Add a label to an entity; used by the label panel. Administrator only. |

Service field definitions are in
[`custom_components/oasira_b2b/services.yaml`](custom_components/oasira_b2b/services.yaml).

## Frontend panels

The packaged panels are:

- `config-panel.js`: account controls and Matter Hub bridge information, with a
  factory reset action for each bridge.
- `area-panel.js`: filter entities by domain and drag entities between areas.
- `label-panel.js`: filter entities by domain and drag entities to labels.

To expose these as sidebar panels, make sure the files from
`custom_components/oasira_b2b/www/oasira_b2b` are available under
`/config/www/oasira_b2b`, then add the following to `configuration.yaml`:

```yaml
panel_custom:
  - name: oasira-config-panel
    sidebar_title: Oasira Config
    sidebar_icon: mdi:alpha-e-box-outline
    url_path: oasira-config-panel
    module_url: /local/oasira_b2b/config-panel.js

  - name: oasira-area-panel
    sidebar_title: Device Areas
    sidebar_icon: mdi:home-group
    url_path: oasira-area-panel
    module_url: /local/oasira_b2b/area-panel.js

  - name: oasira-label-panel
    sidebar_title: Entity Labels
    sidebar_icon: mdi:label
    url_path: oasira-label-panel
    module_url: /local/oasira_b2b/label-panel.js
```

Restart Home Assistant after changing the panel configuration. The Matter
panel obtains bridge information from the Matter Hub API on the local network.

## Included resources

- Automation blueprints: `custom_components/oasira_b2b/blueprints/`
- Frontend assets: `custom_components/oasira_b2b/www/oasira_b2b/`
- Theme: `custom_components/oasira_b2b/themes/`

### Configuration Backups

Once the node is enrolled (or the Care API URL/key options are set), **Oasira Care** appears as a backup location in Home Assistant's native backup feature (Settings → System → Backups). Select it as a location in the automatic backup settings, or when creating a manual backup. Home Assistant creates, encrypts, schedules and prunes the backups (retention is configured in HA), and restoring from an Oasira Care backup uses HA's normal restore flow. Backups are stored in the Care API, which limits uploads to 100 MB; larger backups fail with an error.

## Requirements

- Home Assistant **2025.1+**
- `recorder` integration enabled
- Internet connection for cloud features
- Optional Care API URL and facility ingest key for Care API streaming

Python requirements are declared in
[`custom_components/oasira_b2b/manifest.json`](custom_components/oasira_b2b/manifest.json)
and are installed by Home Assistant.

## Support

- [Oasira documentation](https://www.oasira.ai/)
- [Report an issue](https://github.com/EffortlessHome/Oasira_B2B/issues)
