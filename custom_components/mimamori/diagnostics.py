"""Diagnostics download: the settings and the last answer, without secrets or names.

Users attach this file to issues, so the token, addresses, host names, serial numbers and
check targets are removed.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_TOKEN, CONF_URL
from homeassistant.core import HomeAssistant

from .coordinator import MimamoriConfigEntry

TO_REDACT = {
    CONF_API_TOKEN, CONF_URL, "url", "name", "hostname", "host", "location", "serial", "target",
    "text", "title", "headline", "summary", "last_error", "error", "image", "kernel",
    "device", "problems",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: MimamoriConfigEntry
                                             ) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": {"data": async_redact_data(dict(entry.data), TO_REDACT),
                  "options": dict(entry.options)},
        "last_update_success": coordinator.last_update_success,
        "summary": async_redact_data(coordinator.data.raw, TO_REDACT),
    }
