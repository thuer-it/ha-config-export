"""Tests for config_export.markdown."""

import json

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar, entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.config_export.const import DOMAIN, SECTIONS
from custom_components.config_export.markdown import device_entry_ids


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


async def _setup(hass: HomeAssistant):
    assert await async_setup_component(hass, "automation", {
        "automation": [{
            "id": "a1", "alias": "Test Auto",
            "triggers": [{"trigger": "state", "entity_id": "light.x"}],
            "actions": [{"action": "notify.notify", "data": {"message": "hi", "api_key": "SECRET123"}}],
        }]
    })
    assert await async_setup_component(hass, "script", {
        "script": {"s1": {"alias": "Skript 1", "sequence": [{"delay": 1}]}}
    })
    assert await async_setup_component(hass, "lovelace", {})
    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_markdown_all(hass: HomeAssistant, tmp_path) -> None:
    await _setup(hass)
    area = ar.async_get(hass).async_create("Büro")
    er.async_get(hass).async_get_or_create("light", "demo", "u1", suggested_object_id="buero")
    er.async_get(hass).async_update_entity("light.buero", area_id=area.id)
    hass.states.async_set("light.buero", "on")

    # UI helper in .storage
    sd = hass.config.path(".storage")
    import os
    os.makedirs(sd, exist_ok=True)
    with open(os.path.join(sd, "input_boolean"), "w") as fh:
        json.dump({"version": 1, "data": {"items": [{"id": "gast", "name": "Gast da", "icon": "mdi:x"}]}}, fh)

    res = await hass.services.async_call(DOMAIN, "markdown", {"detail": "full", "include_states": True, "sections": SECTIONS},
                                         blocking=True, return_response=True)
    md = res["markdown"]
    print(md)
    assert "## Automationen" in md and "automation.test_auto" in md
    assert "SECRET123" not in md and "**REDACTED**" in md
    assert "script.s1" in md
    assert "### Büro" in md and "light.buero" in md and "| on |" in md
    assert "Gast da" in md
    assert "## Dashboards" in md


async def test_filter_domain(hass: HomeAssistant) -> None:
    await _setup(hass)
    er.async_get(hass).async_get_or_create("light", "demo", "u1", suggested_object_id="a")
    er.async_get(hass).async_get_or_create("switch", "demo", "u2", suggested_object_id="b")
    res = await hass.services.async_call(DOMAIN, "markdown",
                                         {"sections": ["entities"], "filter_domain": "light"},
                                         blocking=True, return_response=True)
    assert "light.a" in res["markdown"] and "switch.b" not in res["markdown"]
    assert "## Automationen" not in res["markdown"]


async def test_non_admin_rejected(hass: HomeAssistant, hass_read_only_user) -> None:
    from homeassistant.core import Context
    from homeassistant.exceptions import Unauthorized
    await _setup(hass)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(DOMAIN, "markdown", {}, blocking=True, return_response=True,
                                       context=Context(user_id=hass_read_only_user.id))


async def test_default_sections_and_disabled(hass: HomeAssistant) -> None:
    await _setup(hass)
    reg = er.async_get(hass)
    reg.async_get_or_create("light", "demo", "u1", suggested_object_id="on1")
    reg.async_get_or_create("light", "demo", "u2", suggested_object_id="off1",
                            disabled_by=er.RegistryEntryDisabler.USER)
    res = await hass.services.async_call(DOMAIN, "markdown", {}, blocking=True, return_response=True)
    assert "## Entitäten" not in res["markdown"] and "## Geräte" not in res["markdown"]
    res = await hass.services.async_call(DOMAIN, "markdown", {"sections": ["entities"]},
                                         blocking=True, return_response=True)
    assert "light.on1" in res["markdown"] and "light.off1" not in res["markdown"]
    res = await hass.services.async_call(DOMAIN, "markdown",
                                         {"sections": ["entities"], "include_disabled": True},
                                         blocking=True, return_response=True)
    assert "light.off1" in res["markdown"]


def test_device_entry_ids_new_and_old_style() -> None:
    import attr

    @attr.s(frozen=True)
    class NewDev:
        config_entry_id = attr.ib()

        @property
        def config_entries(self):
            raise AssertionError("deprecated shim must not be used")

    @attr.s(frozen=True)
    class OldDev:
        config_entries = attr.ib()

    assert device_entry_ids(NewDev("e1")) == {"e1"}
    assert device_entry_ids(NewDev(None)) == set()
    assert device_entry_ids(OldDev({"a", "b"})) == {"a", "b"}
