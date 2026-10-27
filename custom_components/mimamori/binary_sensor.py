"""Binary sensors: yes/no states such as "a problem", "online" or "reboot required"."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import MimamoriConfigEntry, MimamoriData
from .entity import MimamoriEntity, add_entities_as_they_appear, safe, timestamp

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class MimamoriBinaryDescription(BinarySensorEntityDescription):
    is_on_fn: Callable[[dict], bool | None]
    attrs_fn: Callable[[dict], dict[str, Any]] | None = None
    exists_fn: Callable[[dict], bool] = lambda item: True


SERVER_BINARY: tuple[MimamoriBinaryDescription, ...] = (
    MimamoriBinaryDescription(
        key="problem", translation_key="problem", device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda r: r["status"].get("severity") not in (None, "none"),
        attrs_fn=lambda r: {"severity": r["status"].get("severity"),
                            "headline": r["status"].get("headline")}),
)

HOST_BINARY: tuple[MimamoriBinaryDescription, ...] = (
    MimamoriBinaryDescription(
        key="online", translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        is_on_fn=lambda h: bool(h.get("online")),
        attrs_fn=lambda h: {"last_seen": timestamp(h.get("last_seen"))}),
    MimamoriBinaryDescription(
        key="reboot_required", translation_key="reboot_required",
        is_on_fn=lambda h: bool(h.get("reboot_required"))),
)

DRIVE_BINARY: tuple[MimamoriBinaryDescription, ...] = (
    MimamoriBinaryDescription(
        key="problem", translation_key="drive_problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda d: d.get("status") != "healthy",
        attrs_fn=lambda d: {"status": d.get("status"), "summary": d.get("summary") or None}),
    MimamoriBinaryDescription(
        key="firmware_update", translation_key="firmware_update",
        device_class=BinarySensorDeviceClass.UPDATE,
        is_on_fn=lambda d: d.get("firmware_update") is not None,
        attrs_fn=lambda d: {"severity": d.get("firmware_update"),
                            "firmware": d.get("firmware")}),
)


def _monitor_up(m: dict) -> bool | None:
    status = m.get("status")
    return True if status == "up" else False if status == "down" else None  # paused, pending


def _push_problem(p: dict) -> bool | None:
    status = p.get("status")
    if status in ("late", "failed"):
        return True
    return False if status == "up" else None  # new, paused


MONITOR_BINARY: tuple[MimamoriBinaryDescription, ...] = (
    MimamoriBinaryDescription(
        key="status", translation_key="monitor_status",
        device_class=BinarySensorDeviceClass.CONNECTIVITY, is_on_fn=_monitor_up,
        attrs_fn=lambda m: {"status": m.get("status"), "target": m.get("target"),
                            "kind": m.get("kind"), "last_error": m.get("last_error") or None,
                            "last_check": timestamp(m.get("last_check"))}),
    MimamoriBinaryDescription(
        key="certificate_expiring", translation_key="certificate_expiring",
        device_class=BinarySensorDeviceClass.PROBLEM,
        is_on_fn=lambda m: bool(m.get("certificate_expiring")),
        exists_fn=lambda m: m.get("certificate_expires") is not None),
)

PUSH_BINARY: tuple[MimamoriBinaryDescription, ...] = (
    MimamoriBinaryDescription(
        key="problem", translation_key="push_problem",
        device_class=BinarySensorDeviceClass.PROBLEM, is_on_fn=_push_problem,
        attrs_fn=lambda p: {"status": p.get("status"),
                            "last_ping": timestamp(p.get("last_ping"))}),
    MimamoriBinaryDescription(
        key="running", translation_key="running", device_class=BinarySensorDeviceClass.RUNNING,
        is_on_fn=lambda p: bool(p.get("running"))),
)

ITEM_BINARY = {"hosts": HOST_BINARY, "drives": DRIVE_BINARY, "monitors": MONITOR_BINARY,
               "push_checks": PUSH_BINARY}


async def async_setup_entry(hass: HomeAssistant, entry: MimamoriConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data

    def build(data: MimamoriData):
        for description in SERVER_BINARY:
            yield MimamoriBinarySensor(coordinator, description)
        for collection, descriptions in ITEM_BINARY.items():
            for item_id, item in getattr(data, collection).items():
                for description in descriptions:
                    if safe(description.exists_fn, item):
                        yield MimamoriBinarySensor(coordinator, description, collection, item_id)

    add_entities_as_they_appear(coordinator, entry, async_add_entities, build)


class MimamoriBinarySensor(MimamoriEntity, BinarySensorEntity):
    entity_description: MimamoriBinaryDescription

    @property
    def is_on(self) -> bool | None:
        return safe(self.entity_description.is_on_fn, self.item)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return safe(self.entity_description.attrs_fn, self.item)
