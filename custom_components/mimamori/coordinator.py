"""Polls mimamori and keeps the answer for all entities."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import InvalidAuth, MimamoriClient, MimamoriError
from .const import CONF_SCAN_SECONDS, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type MimamoriConfigEntry = ConfigEntry[MimamoriCoordinator]


def _by_id(items: Any) -> dict:
    if not isinstance(items, list):
        return {}
    return {i["id"]: i for i in items
            if isinstance(i, dict) and isinstance(i.get("id"), (int, str))}


@dataclass
class MimamoriData:
    """The summary, with each list indexed by the item's ID."""

    raw: dict[str, Any]
    hosts: dict[str, dict] = field(default_factory=dict)
    drives: dict[int, dict] = field(default_factory=dict)
    monitors: dict[int, dict] = field(default_factory=dict)
    push_checks: dict[int, dict] = field(default_factory=dict)
    docker_images: dict[int, dict] = field(default_factory=dict)

    @classmethod
    def from_summary(cls, raw: dict[str, Any]) -> MimamoriData:
        return cls(raw=raw, hosts=_by_id(raw.get("hosts")), drives=_by_id(raw.get("drives")),
                   monitors=_by_id(raw.get("monitors")),
                   push_checks=_by_id(raw.get("push_checks")),
                   docker_images=_by_id(raw.get("docker_images")))

    def section(self, name: str) -> dict:
        """A dict from the top level of the answer, {} if it is missing."""
        value = self.raw.get(name)
        return value if isinstance(value, dict) else {}


class MimamoriCoordinator(DataUpdateCoordinator[MimamoriData]):
    config_entry: MimamoriConfigEntry

    def __init__(self, hass: HomeAssistant, entry: MimamoriConfigEntry,
                 client: MimamoriClient) -> None:
        seconds = entry.options.get(CONF_SCAN_SECONDS)
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN,
            update_interval=timedelta(seconds=seconds) if seconds else DEFAULT_SCAN_INTERVAL)
        self.client = client
        # Registry ids of the server and host devices, see entity._via()
        self.parent_device_ids: dict[tuple[str, str], str] = {}

    async def _async_update_data(self) -> MimamoriData:
        try:
            raw = await self.client.summary()
        except InvalidAuth as err:
            # Home Assistant asks the user for a new token
            raise ConfigEntryAuthFailed("The API token was rejected") from err
        except MimamoriError as err:
            raise UpdateFailed(f"mimamori: {err.__class__.__name__} {err}".strip()) from err
        return MimamoriData.from_summary(raw)
