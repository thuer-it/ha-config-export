# Config Export for Home Assistant

Returns your Home Assistant configuration as **Markdown** through a single service call with response data. Built for giving AI assistants (Claude, ChatGPT, … via MCP / REST / WebSocket) compact context about an instance instead of dozens of API calls.

Read-only: the integration never changes anything.

## What is exported

| Section | Content |
|---|---|
| `overview` | counts of floors, areas, labels, integrations, devices, entities |
| `floors`, `areas`, `labels` | registries |
| `integrations` | config entries: domain, title, state, device/entity counts (no entry data) |
| `devices` | grouped by area: name, manufacturer, model, integration, labels |
| `entities` | grouped by area: entity_id, name, integration, disabled/hidden, labels, optional state |
| `automations`, `scripts` | list; with `detail: full` the complete config as YAML |
| `helpers` | UI helpers (input_*, counter, timer, schedule) |
| `dashboards` | list; with `detail: full` the complete Lovelace config |

Values of keys that look secret (`password`, `token`, `api_key`, `secret`, `auth`, `pin`, `webhook_id`, …) are replaced by `**REDACTED**`. `secrets.yaml`, auth storage and config entry data are never read.

## Installation

### HACS
1. HACS → ⋮ → *Custom repositories* → `https://github.com/thuer-it/ha-config-export`, type *Integration*
2. Download **Config Export**, restart Home Assistant

### Manual
Copy `custom_components/config_export` into `<config>/custom_components/` and restart.

### Setup
Settings → Devices & services → *Add integration* → **Config Export** (no options).

## Usage

```yaml
action: config_export.markdown
data:
  sections: [areas, automations]   # optional, default: all except devices/entities
  filter_area: living_room              # optional, area_id
  filter_domain: light             # optional
  filter_integration: zha          # optional
  include_states: true             # optional, default false
  include_disabled: false          # optional, default false (devices/entities)
  detail: full                     # summary (default) | full
response_variable: export
```

Response: `markdown`, `chars`, `ha_version`, `generated`, `sections`.

The service only accepts calls from admin users and requires `return_response`.

## Notes
- `devices` and `entities` are only exported when requested in `sections` – on real instances they are large (example: ~1,500 devices / ~8,800 entities ≈ 1 MB of Markdown). Combine them with `filter_area`, `filter_domain` or `filter_integration`.
- Disabled devices/entities are skipped unless `include_disabled: true`.
- The default dashboard in auto-generated mode is reported as not readable (`ConfigNotFound`).

## License
MIT
