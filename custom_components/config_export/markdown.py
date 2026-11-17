"""Build Markdown from Home Assistant registries and configs (read-only)."""

from __future__ import annotations

from collections import defaultdict
import json
import logging
from pathlib import Path
from typing import Any

import attr

from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    floor_registry as fr,
    label_registry as lr,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.yaml import dump as yaml_dump

from .const import DEFAULT_SECTIONS, HELPER_STORAGE_KEYS, REDACTED, SECRET_KEY_RE

_LOGGER = logging.getLogger(__name__)
NO_AREA = "(ohne Bereich)"


# --------------------------------------------------------------- helpers
def redact(obj: Any) -> Any:
    """Recursively replace values whose key looks secret."""
    if isinstance(obj, dict):
        return {
            k: (REDACTED if isinstance(k, str) and SECRET_KEY_RE.search(k) else redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, (list, tuple)):
        return [redact(v) for v in obj]
    return obj


def cell(value: Any) -> str:
    """Escape a value for a Markdown table cell."""
    if value is None or value == "":
        return "–"
    if isinstance(value, (set, list, tuple)):
        value = ", ".join(sorted(str(v) for v in value)) or "–"
    return str(value).replace("|", "\\|").replace("\n", " ")


def table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_keine_\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(cell(c) for c in r) + " |" for r in rows]
    return "\n".join(out) + "\n"


def yaml_block(data: Any) -> str:
    return "```yaml\n" + yaml_dump(redact(data)).rstrip() + "\n```\n"


def device_entry_ids(dev: Any) -> set[str]:
    """Config entry ids of a device.

    HA >= 2026.11 stores a single ``config_entry_id``; the old
    ``config_entries`` property became a deprecated shim that reports usage
    (stack inspection: slow, logs warnings), so avoid it when possible.
    """
    try:
        has_single = "config_entry_id" in attr.fields_dict(type(dev))
    except (TypeError, attr.exceptions.NotAnAttrsClassError):
        has_single = hasattr(dev, "config_entry_id")
    if has_single:
        cid = dev.config_entry_id
        return {cid} if cid else set()
    return set(getattr(dev, "config_entries", ()) or ())


def _read_storage(path: Path) -> Any:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------ main entry
async def async_build_markdown(hass: HomeAssistant, opts: dict[str, Any]) -> dict[str, Any]:
    """Return {'markdown': str, ...} for the requested sections."""
    sections = opts.get("sections") or DEFAULT_SECTIONS
    full = opts.get("detail", "summary") == "full"
    f_area = opts.get("filter_area")
    f_domain = opts.get("filter_domain")
    f_integ = opts.get("filter_integration")
    with_states = opts.get("include_states", False)
    with_disabled = opts.get("include_disabled", False)

    areg, dreg, ereg = ar.async_get(hass), dr.async_get(hass), er.async_get(hass)
    freg, lreg = fr.async_get(hass), lr.async_get(hass)

    area_name = {a.id: a.name for a in areg.async_list_areas()}
    label_name = {l.label_id: l.name for l in lreg.async_list_labels()}
    entry_domain = {e.entry_id: e.domain for e in hass.config_entries.async_entries()}

    def dev_area(dev: dr.DeviceEntry | None) -> str | None:
        return dev.area_id if dev else None

    def ent_area(ent: er.RegistryEntry) -> str | None:
        return ent.area_id or dev_area(dreg.async_get(ent.device_id) if ent.device_id else None)

    def labels(ids: set[str]) -> list[str]:
        return [label_name.get(i, i) for i in ids]

    def dev_ok(dev: dr.DeviceEntry) -> bool:
        if not with_disabled and dev.disabled_by:
            return False
        if f_area and dev.area_id != f_area:
            return False
        if f_integ and f_integ not in {entry_domain.get(c) for c in device_entry_ids(dev)}:
            return False
        return True

    def ent_ok(ent: er.RegistryEntry) -> bool:
        if not with_disabled and ent.disabled_by:
            return False
        if f_domain and ent.domain != f_domain:
            return False
        if f_area and ent_area(ent) != f_area:
            return False
        if f_integ and ent.platform != f_integ:
            return False
        return True

    md: list[str] = [f"# Home Assistant – Konfiguration\n"]
    md.append(
        f"Stand: {dt_util.now().isoformat(timespec='seconds')} · HA {HA_VERSION}"
        + (f" · Filter: area={f_area} domain={f_domain} integration={f_integ}"
           if (f_area or f_domain or f_integ) else "")
        + "\n"
    )

    # -------- overview
    if "overview" in sections:
        md.append("\n## Übersicht\n")
        md.append(table(["Objekt", "Anzahl"], [
            ["Etagen", len(list(freg.async_list_floors()))],
            ["Bereiche", len(area_name)],
            ["Labels", len(label_name)],
            ["Integrationen (Einträge)", len(entry_domain)],
            ["Geräte", len(dreg.devices)],
            ["Entitäten (Registry)", len(ereg.entities)],
            ["Zustände", len(hass.states.async_all())],
        ]))
        md.append(
            "\n_devices/entities sind groß: nur auf Anfrage (sections) und am besten "
            "mit filter_area/filter_domain/filter_integration; deaktivierte nur mit "
            "include_disabled._\n"
        )

    # -------- floors
    if "floors" in sections:
        md.append("\n## Etagen\n")
        md.append(table(["floor_id", "Name", "Ebene"], [
            [f.floor_id, f.name, f.level]
            for f in sorted(freg.async_list_floors(), key=lambda f: (f.level or 0, f.name))
        ]))

    # -------- areas
    if "areas" in sections:
        md.append("\n## Bereiche\n")
        md.append(table(["area_id", "Name", "Etage", "Labels"], [
            [a.id, a.name, a.floor_id, labels(a.labels)]
            for a in sorted(areg.async_list_areas(), key=lambda a: a.name)
            if not f_area or a.id == f_area
        ]))

    # -------- labels
    if "labels" in sections:
        md.append("\n## Labels\n")
        md.append(table(["label_id", "Name", "Beschreibung"], [
            [l.label_id, l.name, l.description]
            for l in sorted(lreg.async_list_labels(), key=lambda l: l.name)
        ]))

    # -------- integrations
    if "integrations" in sections:
        dev_cnt: dict[str, int] = defaultdict(int)
        ent_cnt: dict[str, int] = defaultdict(int)
        for d in dreg.devices.values():
            for c in device_entry_ids(d):
                dev_cnt[c] += 1
        for e in ereg.entities.values():
            if e.config_entry_id:
                ent_cnt[e.config_entry_id] += 1
        md.append("\n## Integrationen\n")
        md.append(table(["Domain", "Titel", "Status", "deaktiviert", "Geräte", "Entitäten"], [
            [e.domain, e.title, e.state.value, e.disabled_by, dev_cnt[e.entry_id], ent_cnt[e.entry_id]]
            for e in sorted(hass.config_entries.async_entries(), key=lambda e: (e.domain, e.title))
            if not f_integ or e.domain == f_integ
        ]))

    # -------- devices
    if "devices" in sections:
        md.append("\n## Geräte\n")
        grouped: dict[str, list] = defaultdict(list)
        for d in dreg.devices.values():
            if not dev_ok(d):
                continue
            grouped[area_name.get(d.area_id, NO_AREA)].append([
                d.name_by_user or d.name, d.manufacturer, d.model,
                [entry_domain.get(c, c) for c in device_entry_ids(d)],
                d.disabled_by, labels(d.labels), d.id,
            ])
        for area in sorted(grouped):
            md.append(f"\n### {area}\n")
            md.append(table(["Name", "Hersteller", "Modell", "Integration", "deaktiviert", "Labels", "device_id"],
                            sorted(grouped[area], key=lambda r: str(r[0]))))

    # -------- entities
    if "entities" in sections:
        md.append("\n## Entitäten\n")
        grouped = defaultdict(list)
        hdr = ["entity_id", "Name", "Integration", "deaktiviert", "versteckt", "Labels"]
        if with_states:
            hdr.append("Zustand")
        for e in ereg.entities.values():
            if not ent_ok(e):
                continue
            row = [e.entity_id, e.name or e.original_name, e.platform,
                   e.disabled_by, e.hidden_by, labels(e.labels)]
            if with_states:
                st = hass.states.get(e.entity_id)
                row.append(st.state if st else None)
            grouped[area_name.get(ent_area(e), NO_AREA)].append(row)
        for area in sorted(grouped):
            md.append(f"\n### {area}\n")
            md.append(table(hdr, sorted(grouped[area], key=lambda r: r[0])))

    # -------- automations / scripts
    for sec, domain, title in (("automations", "automation", "Automationen"),
                               ("scripts", "script", "Skripte")):
        if sec not in sections:
            continue
        md.append(f"\n## {title}\n")
        component = hass.data.get(domain)
        if component is None:
            md.append("_nicht geladen_\n")
            continue
        items = []
        for ent in component.entities:
            if f_area and ent.registry_entry and ent_area(ent.registry_entry) != f_area:
                continue
            st = hass.states.get(ent.entity_id)
            items.append((ent, st))
        items.sort(key=lambda x: x[0].entity_id)
        md.append(table(["entity_id", "Name", "Zustand", "zuletzt ausgelöst", "id"], [
            [ent.entity_id, st.name if st else ent.name, st.state if st else None,
             st.attributes.get("last_triggered") if st else None,
             (getattr(ent, "raw_config", None) or {}).get("id")]
            for ent, st in items
        ]))
        if full:
            for ent, st in items:
                raw = getattr(ent, "raw_config", None)
                if raw is None:
                    continue
                md.append(f"\n### {ent.entity_id}\n")
                md.append(yaml_block(raw))

    # -------- helpers
    if "helpers" in sections:
        md.append("\n## Helfer (UI)\n")
        storage_dir = Path(hass.config.path(".storage"))
        for key in HELPER_STORAGE_KEYS:
            if f_domain and key != f_domain:
                continue
            data = await hass.async_add_executor_job(_read_storage, storage_dir / key)
            items = ((data or {}).get("data") or {}).get("items") or []
            if not items:
                continue
            md.append(f"\n### {key} ({len(items)})\n")
            if full:
                md.append(yaml_block(items))
            else:
                md.append(table(["id", "Name", "Parameter"], [
                    [i.get("id"), i.get("name"),
                     ", ".join(f"{k}={v}" for k, v in redact(i).items()
                               if k not in ("id", "name", "icon"))]
                    for i in sorted(items, key=lambda i: str(i.get("name")))
                ]))

    # -------- dashboards
    if "dashboards" in sections:
        md.append("\n## Dashboards\n")
        ll = hass.data.get("lovelace")
        dashboards = getattr(ll, "dashboards", None) or {}
        rows, bodies = [], []
        for url_path, dash in sorted(dashboards.items(), key=lambda x: str(x[0])):
            meta = getattr(dash, "config", None) or {}
            rows.append([url_path or "lovelace (Standard)", meta.get("title"),
                         getattr(dash, "mode", None), meta.get("require_admin"),
                         meta.get("show_in_sidebar")])
            if full:
                try:
                    conf = await dash.async_load(False)
                except Exception as err:  # noqa: BLE001 - e.g. ConfigNotFound
                    bodies.append(f"\n### {url_path or 'lovelace'}\n_nicht lesbar: {type(err).__name__}_\n")
                    continue
                bodies.append(f"\n### {url_path or 'lovelace'}\n" + yaml_block(conf))
        md.append(table(["url_path", "Titel", "Modus", "nur Admin", "Seitenleiste"], rows))
        md.extend(bodies)

    text = "".join(md)
    return {
        "markdown": text,
        "chars": len(text),
        "ha_version": HA_VERSION,
        "generated": dt_util.now().isoformat(timespec="seconds"),
        "sections": list(sections),
    }
