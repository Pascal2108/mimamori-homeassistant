# mimamori for Home Assistant

Brings [mimamori](https://github.com/Pascal2108/mimamori) into Home Assistant: the overall state, drive health, hosts, status checks, backups and Docker images as devices and sensors, for dashboards and automations.

The integration only reads. It cannot change anything in mimamori, start a check or read a setting.

> **Beta:** every version below 1.0 is a beta. Entities and their names may still change between versions. Read the release notes before you update.

## What you get

| Device | Entities |
|---|---|
| **mimamori** (the server) | **Status** (`OK` or `Problem`), **Severity** (`All fine`, `Low`, `Medium`, `Critical`, with every open problem as an attribute), counts: open problems, drives with problems, hosts offline, missing security updates, status checks down, backups and jobs with problems, Docker image updates |
| **Each host** | **Agent** online, **Reboot required**, missing security updates, **Disk space** per filesystem (% used, free space as an attribute), last report, operating system |
| **Each drive** (under its host, named like `nas sda`) | **Health** (`Healthy`, `Watch`, `Failing`, `Missing`), **Status** (`OK` or `Problem`), temperature, wear (SSD/NVMe), reallocated and pending sectors (HDD/SSD), media errors (NVMe), power-on time, firmware update recommended |
| **Each status check** | **Status** (connected or not), response time, uptime over 24 hours and 30 days, certificate expiry |
| **Each backup or job** (push check) | **Status** (`Problem` when failed or overdue), running, last success, overdue after |
| **Each Docker image** | An **update** entity: installed and newest version. You update by hand, as in mimamori |

Values a drive does not have (wear on an HDD, sectors on an NVMe) get no entity. New drives, hosts and checks appear by themselves. A device that was removed in mimamori becomes unavailable; delete it under its device page → ⋮ → Delete.

## Requirements

- mimamori **v0.3.5** or newer (the version with Settings → API tokens)
- Home Assistant **2025.3** or newer
- Home Assistant reaches mimamori over the network

## Installation

### With HACS

1. HACS → ⋮ → **Custom repositories**: add `https://github.com/Pascal2108/mimamori-homeassistant`, type **Integration**.
2. Search for **mimamori**, install it and restart Home Assistant.

### By hand

Copy `custom_components/mimamori` into the `custom_components` folder of your Home Assistant configuration and restart Home Assistant.

## Setup

1. In mimamori, open **Settings → API tokens**, create a token named *Home Assistant* and copy it. It is shown only once.
2. In Home Assistant: **Settings → Devices & services → Add integration → mimamori**.
3. Enter the address of mimamori as Home Assistant reaches it and the token.

| Field | |
|---|---|
| Address | The HTTPS address of mimamori, e.g. `https://mimamori.example.com`. Use `http://mimamori:8000` only if Home Assistant and mimamori share one Docker network |
| API token | Starts with `mmr_` |
| Verify the HTTPS certificate | Leave on. Turn off only for a self-signed certificate |

Home Assistant asks mimamori once a minute. Change it under the integration's **Configure** (30 to 3600 seconds).

If the token is revoked, Home Assistant shows a notice and asks for a new one. To change the address, use **⋮ → Reconfigure** on the integration.

## Examples

A notification when anything needs attention:

```yaml
automation:
  - alias: mimamori needs attention
    triggers:
      - trigger: state
        entity_id: sensor.mimamori_severity
        to: [medium, critical]
    actions:
      - action: notify.notify
        data:
          title: mimamori
          message: "{{ state_attr('sensor.mimamori_severity', 'problems') | join('\n') }}"
```

A dashboard card with the overall state and every drive's health:

```yaml
type: entities
title: mimamori
entities:
  - binary_sensor.mimamori_status
  - sensor.mimamori_severity
  - sensor.mimamori_open_problems
  - type: section
  - entity: sensor.nas_sda_health   # each drive's "Health" sensor
```

Entity IDs follow the device names; look them up under the device pages.

## Security

- The token can only read. Create one token per Home Assistant, so that you can revoke it alone in mimamori.
- Home Assistant stores the token in its configuration (`.storage`), like the credentials of other integrations.
- Use HTTPS. Over plain `http://`, the token and all data travel unencrypted; the integration logs a warning then. Redirects are not followed, so the token is never sent anywhere but the address you entered.
- Anyone who can use your Home Assistant sees what mimamori shows, e.g. which hosts lack security updates. Share dashboards accordingly.
- **Voice assistants and LLMs:** drive models, problem texts and OS names come from your hosts. A compromised host could hide instructions in them ("prompt injection"). The integration keeps them out of device and entity names, but they are in the attributes of the **Severity** sensor and on the device pages. Do not expose mimamori entities to an LLM-based assistant that can also control devices (Settings → Voice assistants → Expose); Home Assistant exposes the drive temperatures by default.
- The diagnostics download (device page → ⋮ → Download diagnostics) leaves out the token, addresses, host and drive names, serial numbers and check targets, but check it before attaching it to an issue.

Report security problems privately, see [SECURITY.md](SECURITY.md).

## For developers

The integration uses mimamori's read-only API, described in [docs/api.md](https://github.com/Pascal2108/mimamori/blob/main/docs/api.md) of the mimamori repository. Everything shown here comes from `GET /api/v1/summary`.

## License

Free software under the [AGPL-3.0](LICENSE), without warranty.
