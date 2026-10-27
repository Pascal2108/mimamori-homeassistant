"""mimamori: drive health, systems, status checks, backups and Docker images in Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.const import CONF_API_TOKEN, CONF_URL, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from yarl import URL

from .api import MimamoriClient
from .const import DOMAIN
from .coordinator import MimamoriConfigEntry, MimamoriCoordinator
from .entity import current_device_ids

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR, Platform.UPDATE]


async def async_setup_entry(hass: HomeAssistant, entry: MimamoriConfigEntry) -> bool:
    if URL(entry.data[CONF_URL]).scheme == "http":
        _LOGGER.warning(
            "mimamori at %s is reached over plain HTTP, so the API token travels unencrypted. "
            "That is fine inside one Docker network; otherwise use the HTTPS address.",
            URL(entry.data[CONF_URL]).host)
    elif not entry.data.get(CONF_VERIFY_SSL, True):
        _LOGGER.warning(
            "The HTTPS certificate of mimamori at %s is not verified: anyone who can intercept "
            "the connection can read the API token. Turn the check back on unless the "
            "certificate is self-signed.", URL(entry.data[CONF_URL]).host)
    session = async_get_clientsession(hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, True))
    client = MimamoriClient(session, entry.data[CONF_URL], entry.data[CONF_API_TOKEN])
    coordinator = MimamoriCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: MimamoriConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MimamoriConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(hass: HomeAssistant, entry: MimamoriConfigEntry,
                                           device: dr.DeviceEntry) -> bool:
    """Lets the user delete a device that mimamori no longer has (a removed drive, host or
    check). Devices that still exist cannot be deleted; they would come back at once."""
    ids = {ident for domain, ident in device.identifiers if domain == DOMAIN}
    return not ids & current_device_ids(entry.runtime_data)
