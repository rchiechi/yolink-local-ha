"""YoLink Local integration for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_HUB_IP,
    CONF_NET_ID,
    DEFAULT_HTTP_PORT,
    DEFAULT_MQTT_PORT,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import YoLocalCoordinator, create_coordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up YoLink Local from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    try:
        coordinator = await create_coordinator(
            hass=hass,
            host=entry.data[CONF_HUB_IP],
            client_id=entry.data[CONF_CLIENT_ID],
            client_secret=entry.data[CONF_CLIENT_SECRET],
            net_id=entry.data[CONF_NET_ID],
            http_port=DEFAULT_HTTP_PORT,
            mqtt_port=DEFAULT_MQTT_PORT,
        )
    except Exception:
        _LOGGER.exception("Failed to set up YoLink Local")
        return False

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Perform the first data refresh so the coordinator (and therefore
    # all entities) have valid state before platforms are set up.
    await coordinator.async_config_entry_first_refresh()

    _async_prune_stale_devices(hass, entry, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


@callback
def _async_prune_stale_devices(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: YoLocalCoordinator
) -> None:
    """Remove registry devices the hub no longer enumerates.

    The hub's device list is its pairing table, so a device that is merely
    offline or sleeping stays listed and is never touched; only devices
    actually unpaired from the hub disappear from the enumeration and get
    pruned here. An empty enumeration is treated as a hub fault rather
    than proof that everything was unpaired, so pruning is skipped.
    """
    if not coordinator.devices:
        return

    device_registry = dr.async_get(hass)
    for device_entry in dr.async_entries_for_config_entry(
        device_registry, entry.entry_id
    ):
        if any(
            domain == DOMAIN and device_id in coordinator.devices
            for domain, device_id in device_entry.identifiers
        ):
            continue
        _LOGGER.info(
            "Removing device %s: no longer paired with the hub", device_entry.name
        )
        device_registry.async_update_device(
            device_entry.id, remove_config_entry_id=entry.entry_id
        )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: YoLocalCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
