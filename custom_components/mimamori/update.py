"""Update entities for the Docker images mimamori watches.

They only show that a newer version exists; installing stays with you, as in mimamori.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MimamoriConfigEntry, MimamoriData
from .entity import MimamoriEntity, add_entities_as_they_appear, timestamp

PARALLEL_UPDATES = 0

IMAGE = UpdateEntityDescription(key="image", name=None)  # named like its device


async def async_setup_entry(hass: HomeAssistant, entry: MimamoriConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data

    def build(data: MimamoriData):
        for image_id in data.docker_images:
            yield DockerImageUpdate(coordinator, IMAGE, "docker_images", image_id)

    add_entities_as_they_appear(coordinator, entry, async_add_entities, build)


class DockerImageUpdate(MimamoriEntity, UpdateEntity):
    _attr_translation_key = "docker_image"

    @property
    def installed_version(self) -> str | None:
        return (self.item or {}).get("version")

    @property
    def latest_version(self) -> str | None:
        item = self.item or {}
        if item.get("state") in ("error", "pending"):
            return None  # not known yet: shown as unknown, not as up to date
        return item.get("latest") or item.get("version")

    @property
    def title(self) -> str | None:
        return (self.item or {}).get("image")

    @property
    def release_url(self) -> str | None:
        return (self.item or {}).get("url")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        item = self.item
        if item is None:
            return None
        return {"state": item.get("state"), "last_checked": timestamp(item.get("checked")),
                "error": item.get("error") or None}
