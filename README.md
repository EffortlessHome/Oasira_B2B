# Oasira Business

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-1.0.1-blue.svg)](https://github.com/EffortlessHome/Oasira_B2B)

Oasira Business is a Home Assistant integration focused on security orchestration, area-aware automation, and timeline events.

## Core Capabilities

- Security and alarm coordination with services for pending confirmation, cancel, and status checks
- Area-based automation features including presence workflows, sleep mode support, and entity area updates
- Motion and monitoring automation support with entity grouping and routine orchestration
- Alert and event logging services for operational visibility
- Timeline event workflows for camera snapshots, video clips, person events, review/favorite updates, and cleanup
- Firebase configuration and push notification integration support
- Deployable frontend assets and blueprints included in the integration package

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Add this repository as a custom repository
3. Search for Oasira Business and install
4. Restart Home Assistant
5. Go to Settings > Devices and Services and add Oasira Business

### Manual Installation

1. Copy custom_components/oasira_b2b into your Home Assistant custom_components directory
2. Restart Home Assistant
3. Add Oasira Business from Settings > Devices and Services

## Configuration Overview

Each Home Assistant instance is enrolled as a hub of an Oasira Care facility with a one-time enrollment code (one hub per instance).

## Service Coverage

The integration exposes service groups for:

- Alarm and operations: clean_motion_files, create_event, cancel_alarm, get_alarm_status, confirm_pending_alarm, create_alert, update_entity
- Labels and deployment: add_label_to_entity, deploy_latest_config, get_firebase_config
- Timeline: record_video_clip, create_timeline_event, summarize_timeline_period

For full service schemas and fields, see custom_components/oasira_b2b/services.yaml.

## Requirements

- Home Assistant with config flow support
- Recorder integration enabled
- Network access to the Oasira Care API

Python dependencies are declared in custom_components/oasira_b2b/manifest.json and installed by Home Assistant.

## Support

- Documentation: https://www.oasira.ai/
- Issues: https://github.com/EffortlessHome/Oasira_b2b/issues

## Configuration

### Initial Setup

1. After installation, go to Configuration > Integrations
2. Click the "+" button and search for "Oasira"
3. Enter your Oasira account credentials
4. Select the system you want to configure (if you have multiple systems)

### Configuration.yaml changes

Add the following configuration to your Home Assistant configuration.yaml file:

```yaml
homeassistant:
  allowlist_external_dirs:
    - /media
    - /config/www/oasira_b2b

panel_custom:
  - name: Oasira-config-panel
    sidebar_title: Oasira Config
    sidebar_icon: mdi:alpha-e-box-outline
    url_path: oasira-config-panel
    module_url: /local/oasira_b2b/config-panel.js

  - name: Oasira-area-panel
    url_path: oasira-area-panel
    module_url: /local/oasira_b2b/area-panel.js

  - name: Oasira-label-panel
    url_path: oasira-label-panel
    module_url: /local/oasira_b2b/label-panel.js
```

After adding the configuration, restart Home Assistant for changes to take effect.

### Required Information

- **API URL**: base URL of the Oasira Care API (without `/v1`)
- **Enrollment code**: one-time code generated in Oasira Care (Facility → Hub Provisioning)

### Requirements

- Home Assistant **2024.1+**
- `recorder` component enabled
- Internet connection for cloud features

---

## 🏗️ Architecture: Local-First by Design

```
┌─────────────────────────────────────┐
│           Your Home Network         │
│                                     │
│  ┌──────────────┐  ┌────────────┐  │
│  │Home Assistant │──│Oasira│ │
│  │   (local)     │  │ (local)    │  │
│  └──────┬───────┘  └─────┬──────┘  │
│         │                │         │
│    Local Automations    Local UI    │
│    Local Security       Local Data  │
└─────────┬────────────────┬─────────┘
          │   Encrypted    │
          └───── Cloud ────┘
        (remote access only)
```

✅ All automations run **locally** — no cloud dependency
✅ Your data **stays on your hardware**
✅ Cloud used **only** for secure remote access & optional monitoring


