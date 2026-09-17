"""Sensors for Meebook Bridge - én sensor pr. fanget endpoint."""

import hashlib
import json
import logging
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def pretty_name(path: str) -> str:
    parts = [p for p in path.strip("/").split("/") if p and p != "rest" and not p.isdigit()]
    label = " ".join(parts) if parts else path.strip("/")
    return f"Meebook {label.replace('_', ' ').replace('-', ' ').title()}"


def _short(value, limit=200):
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + "..."
    return value


def summarize(path: str, body):
    """Returner (state, attributes) for en fanget resource."""
    attrs = {"path": path}

    if not isinstance(body, dict):
        return str(body), attrs

    attrs["keys"] = sorted(body.keys())
    for field, value in body.items():
        if isinstance(value, list):
            attrs[f"{field}_count"] = len(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            attrs[field] = _short(value)

    attrs["json"] = json.dumps(body, ensure_ascii=False, default=str)[:100_000]

    items = body.get("items")

    if path == "/rest/related/students":
        if items:
            return ", ".join(i.get("name", "") for i in items[:3]), attrs
        return "Ingen", attrs

    if path == "/rest/annualplans/latest":
        if items:
            it = items[0]
            return (
                f"{it.get('groupName', '')} - {', '.join(it.get('categories') or [])}",
                attrs,
            )
        return "Ingen plan", attrs

    if path == "/rest/annualplans":
        if items:
            return f"{len(items)} planer", attrs
        return "0", attrs

    if path == "/rest/notifications":
        if items:
            d = items[0].get("data", {})
            sender = d.get("senderName", "Ukendt")
            cats = ", ".join(d.get("categories") or [])
            return f"{sender} - {cats}" if cats else sender, attrs
        return "Ingen", attrs

    if path == "/rest/weekplan/events":
        return f"{len(body.get('items', []))} events", attrs

    if path == "/rest/yearSpans":
        for y in body.get("items", []):
            if y.get("currentYear"):
                return y.get("name", "?"), attrs
        return "?", attrs

    m = re.match(r"/rest/annualplans/(\d+)$", path)
    if m:
        activities = body.get("activities") or []
        books = body.get("books") or []
        return f"{len(activities)} aktiviteter, {len(books)} bøger", attrs

    return "OK", attrs


class MeebookResourceSensor(CoordinatorEntity, Entity):
    def __init__(self, coordinator, path: str) -> None:
        super().__init__(coordinator)
        digest = hashlib.sha256(path.encode()).hexdigest()[:12]
        self._attr_unique_id = f"meebook_bridge_{digest}"
        self._attr_name = pretty_name(path)
        self._attr_icon = "mdi:school"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "meebook_bridge")},
            name="Meebook",
            manufacturer="Meebook",
            model="Bridge (HA add-on)",
            sw_version="1.0.13",
        )
        self.path = path
        self._apply_state()

    def _apply_state(self):
        body = self.coordinator.data.get("resources", {}).get(self.path)
        if body is None:
            return
        state, attrs = summarize(self.path, body)
        self._attr_native_value = state
        self._attr_extra_state_attributes = attrs

    def _handle_coordinator_update(self) -> None:
        self._apply_state()
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]

    seen = set()
    resources = coordinator.data.get("resources", {})

    def _create_entities():
        new = [p for p in resources if p not in seen]
        if new:
            for p in new:
                seen.add(p)
            async_add_entities([MeebookResourceSensor(coordinator, p) for p in new])

    def _listener():
        resources.update(coordinator.data.get("resources", {}))
        _create_entities()

    coordinator.async_add_listener(_listener)
    _create_entities()