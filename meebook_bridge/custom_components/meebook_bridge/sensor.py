"""Sensors for Meebook Bridge - én sensor pr. fanget endpoint."""

import hashlib
import json
import logging
import re
from datetime import date

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
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


def _pick(d, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return v
    return None


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
    if items is None and isinstance(body, list):
        items = body

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

    if path == "/rest/messagebook/messagebooks":
        n = len(items or [])
        return f"{n} meddelelsesbøger" if n else "Ingen meddelelsesbog", attrs

    if path == "/rest/messagebook/messages":
        if not items:
            return "Ingen beskeder", attrs
        first = items[0]
        sender = _pick(first, "sender", "senderName", "from") or "?"
        text = _pick(first, "text", "content", "body", "title", "subject") or ""
        msg_date = _pick(first, "date", "dateTime", "created")
        preview = _short(f"{sender}: {text}", 120)
        return f"{len(items)} beskeder - {preview}{' (' + msg_date + ')' if msg_date else ''}", attrs

    if path == "/rest/messagebook/participants":
        return f"{len(items or [])}", attrs

    if path == "/rest/messagebook/sections":
        if not items:
            return "Ingen sektioner", attrs
        first = items[0].get("content", {}).get("title") or "?"
        return f"{len(items)} sektion(er) - {first}", attrs

    if path == "/rest/agreements":
        return f"{len(items or [])} aftaler", attrs

    if path == "/rest/annualplanStatuses":
        return f"{len(items or [])} statusser", attrs

    if path == "/rest/bookChapters":
        return f"{len(items or [])} kapitler", attrs

    m2 = re.match(r"/rest/books/(\d+)$", path)
    if m2:
        item = body.get("item", {}) or {}
        title = _pick(body, "title", "name") or _pick(item, "title", "name") or "?"
        return str(title), attrs

    m = re.match(r"/rest/annualplans/(\d+)$", path)
    if m:
        item = body.get("item", {}) or {}
        included = body.get("included", {}) or {}
        activities = included.get("activity", []) or []
        books = included.get("book", []) or []
        statuses = included.get("annualplanStatus", []) or []
        teachers = included.get("teacher", []) or []

        group = item.get("groupName", "")
        cats = ", ".join(item.get("categories") or [])
        title = f"{group} {cats}".strip() or "Plan"
        teacher = teachers[0].get("name") if teachers else ""

        today = date.today().isoformat()
        upcoming = [
            a
            for a in activities
            if (a.get("endDate") or a.get("startDate") or "") >= today
        ]
        upcoming.sort(key=lambda a: a.get("startDate") or "")
        nxt = upcoming[0] if upcoming else None

        is_read = (
            all(s.get("isRead") for s in statuses) if statuses else None
        )

        if nxt:
            state = f"{title} - næste: {nxt.get('title', '?')} {(nxt.get('startDate') or '')}"
        else:
            state = title

        attrs["teacher"] = teacher
        attrs["is_read"] = is_read
        attrs["next_activity"] = (
            f"{nxt.get('title')} {nxt.get('startDate')} - {nxt.get('endDate')}" if nxt else None
        )
        attrs["books_count"] = len(books)
        attrs["activities_count"] = len(activities)
        attrs["books"] = json.dumps(
            [
                {
                    "title": b.get("title"),
                    "description": b.get("description"),
                    "startDate": b.get("startDate"),
                    "endDate": b.get("endDate"),
                }
                for b in books
            ],
            ensure_ascii=False,
        )
        attrs["activities"] = json.dumps(
            [
                {
                    "title": a.get("title"),
                    "description": a.get("description"),
                    "startDate": a.get("startDate"),
                    "endDate": a.get("endDate"),
                }
                for a in activities
            ],
            ensure_ascii=False,
        )
        return state, attrs

    if isinstance(items, list) and items:
        return f"{len(items)} elementer", attrs

    return "OK", attrs


class MeebookResourceSensor(CoordinatorEntity, SensorEntity):
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
            sw_version="1.0.19",
        )
        self.path = path
        self._apply_state()

    def _apply_state(self):
        body = self.coordinator.data.get("resources", {}).get(self.path) if self.coordinator.data else None
        if body is None:
            return
        try:
            state, attrs = summarize(self.path, body)
        except Exception as err:  # noqa: BLE001 - en ressource må ikke tage hele platformen ned
            _LOGGER.error("Fejl i summarize(%s): %s", self.path, err)
            state = "Fejl"
            attrs = {"error": str(err)}
        self._attr_native_value = state
        self._attr_extra_state_attributes = attrs

    def _handle_coordinator_update(self) -> None:
        try:
            self._apply_state()
        finally:
            self.async_write_ha_state()


class MeebookStatusSensor(CoordinatorEntity, SensorEntity):
    """Viser om add-on'en kan nås og hvorfor ikke."""

    _attr_has_entity_name = False

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = "meebook_bridge_status"
        self._attr_name = "Meebook Status"
        self._attr_icon = "mdi:cloud-alert"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "meebook_bridge")},
            name="Meebook",
            manufacturer="Meebook",
            model="Bridge (HA add-on)",
            sw_version="1.0.19",
        )

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self):
        return "OK" if self.coordinator.last_update_success else "Fejl"

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data or {}
        resources = data.get("resources", {})
        try:
            base = self.coordinator.base_url
        except AttributeError:
            base = "?"
        return {
            "base_url": base,
            "addon_kontakt": "OK" if self.coordinator.last_update_success else "FEJL",
            "sidste_fejl": str(self.coordinator.last_exception or "")
            or "ingen",
            "antal_resources": len(resources),
            "sidste_opdatering": str(self.coordinator.last_update_success),
        }

    def _handle_coordinator_update(self) -> None:
        try:
            self._apply_state()
        finally:
            self.async_write_ha_state()

    def _apply_state(self) -> None:
        pass


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
    async_add_entities([MeebookStatusSensor(coordinator)])