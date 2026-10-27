"""Devices and the base class of all mimamori entities.

Devices: the mimamori server, and under it one device per host, drive (under its host),
status check, push check (backup or job) and Docker image.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from typing import Any

from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import MimamoriConfigEntry, MimamoriCoordinator, MimamoriData

# Item lists of the answer -> device kind
COLLECTIONS = {"hosts": "host", "drives": "drive", "monitors": "monitor",
               "push_checks": "push", "docker_images": "image"}


def safe(fn: Callable[[dict], Any], item: dict | None) -> Any:
    """fn(item), or None when the answer has an unexpected shape (a broken or hostile server
    must not break the entity)."""
    if item is None:
        return None
    try:
        return fn(item)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return None


def timestamp(value: Any) -> datetime | None:
    return dt_util.utc_from_timestamp(value) if isinstance(value, (int, float)) and value else None


def device_id(coordinator: MimamoriCoordinator, kind: str, item_id: Any = None) -> str:
    base = coordinator.config_entry.entry_id
    return base if kind == "server" else f"{base}_{kind}_{item_id}"


def current_device_ids(coordinator: MimamoriCoordinator) -> set[str]:
    data = coordinator.data
    ids = {device_id(coordinator, "server")}
    for collection, kind in COLLECTIONS.items():
        ids |= {device_id(coordinator, kind, i) for i in getattr(data, collection)}
    return ids


# Home Assistant 2026.8 links a device to its parent by the parent's registry id
# (via_device_id); older versions take the parent's identifier (via_device)
_VIA_DEVICE_ID = "via_device_id" in DeviceInfo.__annotations__


def _via(coordinator: MimamoriCoordinator, collection: str | None, item: dict | None) -> dict:
    """The link to the parent device (the server, or a drive's host)."""
    parent = device_info(coordinator, collection, item)
    ident = next(iter(parent["identifiers"]))
    if not _VIA_DEVICE_ID:
        return {"via_device": ident}
    cache = coordinator.parent_device_ids
    if ident not in cache:
        # The parent must exist before the child refers to it
        cache[ident] = dr.async_get(coordinator.hass).async_get_or_create(
            config_entry_id=coordinator.config_entry.entry_id, **parent).id
    return {"via_device_id": cache[ident]}


def device_info(coordinator: MimamoriCoordinator, collection: str | None,
                item: dict | None) -> DeviceInfo:
    server = coordinator.data.section("server")
    if collection is None:
        return DeviceInfo(
            identifiers={(DOMAIN, device_id(coordinator, "server"))},
            name="mimamori", manufacturer="mimamori", model="Server",
            sw_version=server.get("version"), configuration_url=server.get("url"),
            entry_type=DeviceEntryType.SERVICE)
    item = item or {}
    kind = COLLECTIONS[collection]
    info = DeviceInfo(identifiers={(DOMAIN, device_id(coordinator, kind, item.get("id")))},
                      manufacturer="mimamori", configuration_url=item.get("url"))
    if kind == "drive" and (host := coordinator.data.hosts.get(item.get("host_id"))):
        info.update(_via(coordinator, "hosts", host))
    else:
        info.update(_via(coordinator, None, None))
    if kind == "host":
        os_info = item.get("os")
        os_name = os_info.get("name") if isinstance(os_info, dict) else None
        info.update(name=item.get("name"), model=os_name or "Host",
                    sw_version=item.get("agent_version") or None,
                    suggested_area=item.get("location") or None)
    elif kind == "drive":
        # Named by host (chosen in mimamori) and device path (checked by mimamori), never by
        # the model: that text comes from the host's agent, and names reach voice assistants
        # and LLMs, which could follow instructions hidden in it (prompt injection)
        device = str(item.get("device") or "").removeprefix("/dev/") or f"drive {item.get('id')}"
        info.update(name=f"{item.get('host')} {device}",
                    manufacturer=None, model=item.get("model") or "Drive",
                    serial_number=item.get("serial") or None,
                    sw_version=item.get("firmware") or None)
    elif kind == "monitor":
        info.update(name=item.get("name"), model=f"Status check ({item.get('kind')})",
                    entry_type=DeviceEntryType.SERVICE)
    elif kind == "push":
        info.update(name=item.get("name"), model="Push check",
                    entry_type=DeviceEntryType.SERVICE)
    else:
        info.update(name=item.get("name"), model=f"Docker image {item.get('image')}",
                    entry_type=DeviceEntryType.SERVICE)
    return info


class MimamoriEntity(CoordinatorEntity[MimamoriCoordinator]):
    """An entity of the server (collection None) or of one item of a list."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MimamoriCoordinator, description: EntityDescription,
                 collection: str | None = None, item_id: Any = None, sub: str = "") -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self.collection, self.item_id = collection, item_id
        kind = COLLECTIONS[collection] if collection else "server"
        parts = [coordinator.config_entry.entry_id, kind]
        if collection:
            parts.append(str(item_id))
        parts.append(description.key)
        if sub:
            parts.append(sub)
        self._attr_unique_id = "_".join(parts)
        self._attr_device_info = device_info(coordinator, collection, self.item)

    @property
    def item(self) -> dict | None:
        """This entity's item in the latest answer; the summary itself for the server."""
        if self.collection is None:
            return self.coordinator.data.raw
        return getattr(self.coordinator.data, self.collection).get(self.item_id)

    @property
    def available(self) -> bool:
        return super().available and self.item is not None


def add_entities_as_they_appear(
        coordinator: MimamoriCoordinator, entry: MimamoriConfigEntry,
        async_add_entities: AddConfigEntryEntitiesCallback,
        build: Callable[[MimamoriData], Iterable[Entity]]) -> None:
    """Adds the entities now and, after every update, those of new drives, hosts or checks."""
    known: set[str] = set()

    @callback
    def check() -> None:
        new = [e for e in build(coordinator.data) if e.unique_id not in known]
        known.update(e.unique_id for e in new if e.unique_id)
        if new:
            async_add_entities(new)

    check()
    entry.async_on_unload(coordinator.async_add_listener(check))
