"""Meebook Bridge integration - poller add-on-API'et og opretter sensorer."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]


class MeebookCoordinator(DataUpdateCoordinator):
    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        self.session = async_get_clientsession(hass)
        self.base_url = f"http://{host}:{port}"
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )

    async def _async_get_json(self, url: str):
        async with self.session.get(url, timeout=10) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _async_update_data(self):
        try:
            resources, health = await asyncio.gather(
                self._async_get_json(self.base_url + "/data"),
                self._async_get_json(self.base_url + "/health"),
            )
        except Exception as err:
            raise UpdateFailed(f"{self.base_url} - {err}") from err
        return {"resources": resources or {}, "health": health}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = MeebookCoordinator(
        hass, entry.data[CONF_HOST], int(entry.data.get(CONF_PORT, 8600))
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except UpdateFailed as err:
        _LOGGER.exception("Meebook Bridge - første opdatering mislykkedes: %s", err)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok