<div align="center">

# 🏠 EffortlessHome

### The Missing Layer for Home Assistant

**Professional security, intelligent automation, and beautiful dashboards — without the YAML.**

[![Get Early Access](https://img.shields.io/badge/🚀_Get_Early_Access-Sign_Up_Now-F97316?style=for-the-badge)](https://www.effortlesshome.co/#cta)
[![HACS](https://img.shields.io/badge/HACS-Custom-orange.svg?style=flat-square)](https://github.com/hacs/integration)
[![Version](https://img.shields.io/badge/version-11-blue.svg?style=flat-square)](https://github.com/effortlesshome/effortlesshome)
[![License](https://img.shields.io/badge/license-MIT-green.svg?style=flat-square)](LICENSE)

<br/>

[Website](https://effortlesshome.co) · [Get Started](https://www.effortlesshome.co/getstarted/) · [Report Issue](https://github.com/effortlesshome/effortlesshome/issues)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=effortlesshome&repository=effortlesshome)

</div>

---

## 😤 The Problem

You love Home Assistant. But let's be honest:

- **Security systems** require dozens of YAML automations stitched together
- **Remote access** means wrestling with DuckDNS, NGINX, ports, and certs
- **Dashboards** look dated and need constant manual tweaking
- **Automation blueprints** are scattered across forums with no consistency

You didn't buy smart devices to spend weekends debugging configs.

---

## ✅ The Solution

**EffortlessHome** is a native Home Assistant integration that gives you a production-grade smart home — installed in minutes, not weekends.

| What You Get | Without EffortlessHome | With EffortlessHome |
|---|---|---|
| **Security System** | DIY YAML alarm + manual sensors | Multi-mode professional alarm, 24/7 monitoring available |
| **Remote Access** | DuckDNS + NGINX + port forwarding | Secure, encrypted — zero config |
| **Dashboard** | Lovelace cards, manual layout | Beautiful, app-like UI across all devices |
| **Automations** | Copy-paste from forums | 38+ curated blueprints, one-click install |
| **Device Setup** | Entity-by-entity configuration | Drag & drop area/label management |

---

## ✨ Key Features

<table>
<tr>
<td width="50%">

### 🛡️ Professional Security
Multi-mode alarm with intelligent triggering, smart sensor grouping, and optional 24/7 professional monitoring.

### 📍 Area-Aware Automation
Dynamic presence detection, sleep modes, and privacy controls — per room, automatically.

### 🧠 38+ Blueprints
Pre-configured automations for security, safety, daily routines, and device management.

### 🌅 Intelligent Routines
Automated good morning, good night, arrive home, and leave home sequences.

</td>
<td width="50%">

### 🔌 Smart Appliance Monitoring
Convert any appliance into a smart device with cycle detection and notifications.

### 📊 Beautiful Dashboard
Modern web interface with native apps for iOS, Android, Apple TV, Android TV, Windows, and Mac.

### 🎨 Custom HA Theme
A polished, cohesive UI designed specifically for EffortlessHome.

### 🛠️ Drag & Drop Config
Easy area and label management — no YAML required.

</td>
</tr>
</table>

---

## 📱 See It In Action

<div align="center">

### Web Dashboard

<img src="app_screenshots/web/1.png" alt="Web Dashboard — Home" width="700"/>

<br/><br/>

<details>
<summary><strong>📱 Mobile (Android & iOS)</strong></summary>
<br/>

<img src="app_screenshots/android/phone/1.png" alt="Android" width="180"/>
<img src="app_screenshots/android/phone/2.png" alt="Android" width="180"/>
<img src="app_screenshots/apple/iphone/1.PNG" alt="iPhone" width="180"/>
<img src="app_screenshots/apple/iphone/2.PNG" alt="iPhone" width="180"/>

</details>

<details>
<summary><strong>📟 Tablet (iPad & Android)</strong></summary>
<br/>

<img src="app_screenshots/android/tablet/1.png" alt="Android Tablet" width="300"/>
<img src="app_screenshots/apple/ipad/1.PNG" alt="iPad" width="300"/>

</details>

<details>
<summary><strong>🖥️ TV & Desktop (Apple TV, Mac, Windows)</strong></summary>
<br/>

<img src="app_screenshots/apple/appletv/1.png" alt="Apple TV" width="400"/>
<img src="app_screenshots/apple/mac/1.png" alt="Mac" width="400"/>
<img src="app_screenshots/windows/1.png" alt="Windows" width="400"/>

</details>

</div>

---

## 🚀 Quick Start

## Installation

### HACS Installation (Recommended)

1. Open HACS in your Home Assistant instance
2. Add this GitHub repo as a custom source: `https://github.com/effortlesshome/effortlesshome`
3. Search for "EffortlessHome"
4. Click Install
5. Restart Home Assistant

### Manual Installation

1. Copy the `effortlesshome` directory to your `custom_components` folder
2. Restart Home Assistant
3. Add the integration via Configuration > Integrations > Add Integration > EffortlessHome

## Configuration

### Initial Setup

1. After installation, go to Configuration > Integrations
2. Click the "+" button and search for "EffortlessHome"
3. Enter your EffortlessHome account credentials
4. Select the system you want to configure (if you have multiple systems)

### Configuration.yaml changes

Add the following configuration to your Home Assistant configuration.yaml file:

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 192.168.1.0/24 (replace with your local network range)
  cors_allowed_origins:
    - https://dash.effortlesshome.co

homeassistant:
  allowlist_external_dirs:
    - /media
    - /config/www/effortlesshome

panel_custom:
  - name: effortlesshome-config-panel
    sidebar_title: EffortlessHome Config
    sidebar_icon: mdi:alpha-e-box-outline
    url_path: effortlesshome-config-panel
    module_url: /local/effortlesshome/config-panel.js

  - name: effortlesshome-area-panel
    url_path: effortlesshome-area-panel
    module_url: /local/effortlesshome/area-panel.js

  - name: effortlesshome-label-panel
    url_path: effortlesshome-label-panel
    module_url: /local/effortlesshome/label-panel.js
```

After adding the configuration, restart Home Assistant for changes to take effect.

### Required Information

- **Email**: Your EffortlessHome account email
- **Password**: Your EffortlessHome account password

### Optional Configuration


📖 **Full setup guide:** [effortlesshome.co/getstarted](https://www.effortlesshome.co/getstarted/)

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
│  │Home Assistant │──│EffortlessHome│ │
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

---

## 🤝 Community & Support

| Resource | Link |
|---|---|
| 📖 Documentation | [effortlesshome.co/get-started](https://www.effortlesshome.co/getstarted/) |
| 🐛 Report Issues | [GitHub Issues](https://github.com/effortlesshome/effortlesshome/issues) |
| 🌐 Website | [effortlesshome.co](https://www.effortlesshome.co) |

---

<div align="center">

### 🚀 Ready to make your home effortless?

[![Get Early Access](https://img.shields.io/badge/🚀_Get_Early_Access-Sign_Up_Now-F97316?style=for-the-badge)](https://www.effortlesshome.co/#cta)

**Join other Home Assistant users who stopped configuring and started living.**

⭐ **Star this repo** to follow updates and show your support!

</div>
