"""Config Export: Home Assistant configuration as Markdown via service response."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import Unauthorized
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, SECTIONS, SERVICE_MARKDOWN
from .markdown import async_build_markdown

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional("sections"): vol.All(cv.ensure_list, [vol.In(SECTIONS)]),
        vol.Optional("filter_area"): cv.string,
        vol.Optional("filter_domain"): cv.string,
        vol.Optional("filter_integration"): cv.string,
        vol.Optional("include_states", default=False): cv.boolean,
        vol.Optional("include_disabled", default=False): cv.boolean,
        vol.Optional("detail", default="summary"): vol.In(["summary", "full"]),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Register the service."""

    async def _handle(call: ServiceCall) -> ServiceResponse:
        user_id = call.context.user_id
        if user_id is not None:
            user = await hass.auth.async_get_user(user_id)
            if user is None or not user.is_admin:
                raise Unauthorized(context=call.context)
        return await async_build_markdown(hass, call.data)

    hass.services.async_register(
        DOMAIN,
        SERVICE_MARKDOWN,
        _handle,
        schema=SERVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the service."""
    hass.services.async_remove(DOMAIN, SERVICE_MARKDOWN)
    return True
