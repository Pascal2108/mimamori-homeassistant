"""Sensors: overall state and counts, and the values of hosts, drives and checks."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DRIVE_STATES, SEVERITIES
from .coordinator import MimamoriConfigEntry, MimamoriData
from .entity import MimamoriEntity, add_entities_as_they_appear, safe, timestamp

PARALLEL_UPDATES = 0  # all values come from the one coordinator request

MAX_LISTED = 25  # problems listed in the attributes of the status sensor


@dataclass(frozen=True, kw_only=True)
class MimamoriSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict], StateType | datetime]
    attrs_fn: Callable[[dict], dict[str, Any]] | None = None
    # Whether the item has this value at all (an HDD has no wear, an NVMe no sectors)
    exists_fn: Callable[[dict], bool] = lambda item: True


def _counts(raw: dict, key: str) -> dict:
    value = (raw.get("counts") or {}).get(key)
    return value if isinstance(value, dict) else {}


def _enum(value: Any, options: list[str]) -> str | None:
    # A value a newer mimamori may add is shown as unknown rather than breaking the sensor
    return value if value in options else None


def _percent(share: Any) -> float | None:
    return round(share * 100, 2) if isinstance(share, (int, float)) else None


SERVER_SENSORS: tuple[MimamoriSensorDescription, ...] = (
    MimamoriSensorDescription(
        key="status", translation_key="status", device_class=SensorDeviceClass.ENUM,
        options=SEVERITIES,
        value_fn=lambda r: _enum(r["status"].get("severity"), SEVERITIES),
        attrs_fn=lambda r: {
            "headline": r["status"].get("headline"),
            "problems": [f"{a.get('severity')}: {a.get('text')}"
                         for a in (r.get("attention") or [])[:MAX_LISTED]],
            "by_kind": r["status"].get("by_kind"),
        }),
    MimamoriSensorDescription(
        key="problems", translation_key="problems", state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: r["status"].get("problems"),
        attrs_fn=lambda r: r["status"].get("by_severity") or {}),
    MimamoriSensorDescription(
        key="drive_problems", translation_key="drive_problems",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: sum(n for s, n in _counts(r, "drives").items() if s != "healthy"),
        attrs_fn=lambda r: _counts(r, "drives")),
    MimamoriSensorDescription(
        key="hosts_offline", translation_key="hosts_offline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: (r.get("counts") or {}).get("hosts_offline")),
    MimamoriSensorDescription(
        key="security_updates", translation_key="security_updates",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: sum(_counts(r, "security_updates").values()),
        attrs_fn=lambda r: dict(_counts(r, "security_updates"), reboot_required=(
            r.get("counts") or {}).get("reboot_required"))),
    MimamoriSensorDescription(
        key="monitors_down", translation_key="monitors_down",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: _counts(r, "monitors").get("down"),
        attrs_fn=lambda r: _counts(r, "monitors")),
    MimamoriSensorDescription(
        key="push_problems", translation_key="push_problems",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: _counts(r, "push_checks").get("late", 0)
        + _counts(r, "push_checks").get("failed", 0),
        attrs_fn=lambda r: _counts(r, "push_checks")),
    MimamoriSensorDescription(
        key="docker_updates", translation_key="docker_updates",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda r: _counts(r, "docker_images").get("available"),
        attrs_fn=lambda r: _counts(r, "docker_images")),
)

HOST_SENSORS: tuple[MimamoriSensorDescription, ...] = (
    MimamoriSensorDescription(
        key="security_updates", translation_key="host_security_updates",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda h: (h.get("security_updates") or {}).get("total"),
        attrs_fn=lambda h: {k: v for k, v in (h.get("security_updates") or {}).items()
                            if k != "total"}
        | {"last_checked": timestamp(h.get("updates_checked"))}),
    MimamoriSensorDescription(
        key="last_report", translation_key="last_report", device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda h: timestamp(h.get("last_report"))),
    MimamoriSensorDescription(
        key="os", translation_key="os", entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda h: (h.get("os") or {}).get("name") or None,
        attrs_fn=lambda h: {"kernel": (h.get("os") or {}).get("kernel")}),
)

DRIVE_SENSORS: tuple[MimamoriSensorDescription, ...] = (
    MimamoriSensorDescription(
        key="health", translation_key="health", device_class=SensorDeviceClass.ENUM,
        options=DRIVE_STATES, value_fn=lambda d: _enum(d.get("status"), DRIVE_STATES),
        attrs_fn=lambda d: {"summary": d.get("summary") or None,
                            "issues": [i.get("text") for i in d.get("issues") or []],
                            "standby": d.get("standby"), "muted": d.get("muted")}),
    MimamoriSensorDescription(
        key="temperature", device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("temperature"),
        exists_fn=lambda d: d.get("temperature") is not None),
    MimamoriSensorDescription(
        key="wear", translation_key="wear", native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("wear_percent"),
        exists_fn=lambda d: d.get("wear_percent") is not None),
    MimamoriSensorDescription(
        key="reallocated_sectors", translation_key="reallocated_sectors",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("reallocated_sectors"),
        exists_fn=lambda d: d.get("reallocated_sectors") is not None),
    MimamoriSensorDescription(
        key="pending_sectors", translation_key="pending_sectors",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("pending_sectors"),
        exists_fn=lambda d: d.get("pending_sectors") is not None),
    MimamoriSensorDescription(
        key="media_errors", translation_key="media_errors",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("media_errors"),
        exists_fn=lambda d: d.get("media_errors") is not None),
    MimamoriSensorDescription(
        key="power_on_hours", translation_key="power_on_hours",
        device_class=SensorDeviceClass.DURATION, native_unit_of_measurement=UnitOfTime.HOURS,
        suggested_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.TOTAL_INCREASING, entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("power_on_hours"),
        exists_fn=lambda d: d.get("power_on_hours") is not None),
)

MONITOR_SENSORS: tuple[MimamoriSensorDescription, ...] = (
    MimamoriSensorDescription(
        key="response_time", translation_key="response_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda m: m.get("response_ms") if m.get("status") == "up" else None),
    MimamoriSensorDescription(
        key="uptime_24h", translation_key="uptime_24h", native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=2,
        value_fn=lambda m: _percent(m.get("uptime_24h"))),
    MimamoriSensorDescription(
        key="uptime_30d", translation_key="uptime_30d", native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=2,
        value_fn=lambda m: _percent(m.get("uptime_30d"))),
    MimamoriSensorDescription(
        key="certificate_expires", translation_key="certificate_expires",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda m: timestamp(m.get("certificate_expires")),
        exists_fn=lambda m: m.get("certificate_expires") is not None),
)

PUSH_SENSORS: tuple[MimamoriSensorDescription, ...] = (
    MimamoriSensorDescription(
        key="last_success", translation_key="last_success",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda p: timestamp(p.get("last_success"))),
    MimamoriSensorDescription(
        key="deadline", translation_key="deadline", device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda p: timestamp(p.get("deadline"))),
)

ITEM_SENSORS = {"hosts": HOST_SENSORS, "drives": DRIVE_SENSORS, "monitors": MONITOR_SENSORS,
                "push_checks": PUSH_SENSORS}


async def async_setup_entry(hass: HomeAssistant, entry: MimamoriConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data

    def build(data: MimamoriData):
        for description in SERVER_SENSORS:
            yield MimamoriSensor(coordinator, description)
        for collection, descriptions in ITEM_SENSORS.items():
            for item_id, item in getattr(data, collection).items():
                for description in descriptions:
                    if safe(description.exists_fn, item):
                        yield MimamoriSensor(coordinator, description, collection, item_id)
        for host_id, host in data.hosts.items():
            for fs in host.get("filesystems") or []:
                if isinstance(fs, dict) and fs.get("name"):
                    yield FilesystemSensor(coordinator, host_id, fs["name"])

    add_entities_as_they_appear(coordinator, entry, async_add_entities, build)


class MimamoriSensor(MimamoriEntity, SensorEntity):
    entity_description: MimamoriSensorDescription

    @property
    def native_value(self) -> StateType | datetime:
        return safe(self.entity_description.value_fn, self.item)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return safe(self.entity_description.attrs_fn, self.item)


FILESYSTEM = SensorEntityDescription(
    key="filesystem", translation_key="filesystem", native_unit_of_measurement=PERCENTAGE,
    state_class=SensorStateClass.MEASUREMENT)


class FilesystemSensor(MimamoriEntity, SensorEntity):
    """Used space of one filesystem of a host, in percent like df."""

    def __init__(self, coordinator, host_id: str, name: str) -> None:
        super().__init__(coordinator, FILESYSTEM, "hosts", host_id, sub=name)
        self.fs_name = name
        self._attr_translation_placeholders = {"name": name}

    @property
    def fs(self) -> dict | None:
        host = self.item
        return next((f for f in (host or {}).get("filesystems") or []
                     if isinstance(f, dict) and f.get("name") == self.fs_name), None)

    @property
    def available(self) -> bool:
        return super().available and self.fs is not None

    @property
    def native_value(self) -> StateType:
        return (self.fs or {}).get("used_percent")

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fs = self.fs
        if fs is None:
            return None
        gib = lambda n: round(n / 1024**3, 1) if isinstance(n, (int, float)) else None  # noqa: E731
        return {"level": fs.get("level"), "type": fs.get("type"),
                "free_gib": gib(fs.get("free")), "used_gib": gib(fs.get("used")),
                "total_gib": gib(fs.get("total"))}
