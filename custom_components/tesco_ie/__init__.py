"""The Tesco Ireland integration."""

from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    SERVICE_ADD_TO_BASKET,
    SERVICE_INGEST_RECEIPT,
    SERVICE_REMOVE_FROM_INVENTORY,
    SERVICE_SEARCH_PRODUCTS,
)
from .tesco_api import TescoAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Track if services have been registered globally
SERVICES_REGISTERED = False


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tesco Ireland from a config entry."""
    # Note: Home Assistant encrypts config entry data automatically
    # Passwords are not stored in plaintext in storage
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]

    api = TescoAPI(email, password)

    try:
        await api.async_login()
    except Exception as err:
        _LOGGER.error("Failed to authenticate with Tesco")
        raise ConfigEntryAuthFailed from err

    async def async_update_data():
        """Fetch data from Tesco API."""
        try:
            return await api.async_get_data()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(minutes=30),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services globally (only once)
    await async_setup_services(hass)

    return True


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for Tesco integration (global, not per-entry)."""
    global SERVICES_REGISTERED

    if SERVICES_REGISTERED:
        return

    async def handle_add_to_basket(call: ServiceCall) -> None:
        """Handle add to basket service."""
        product_name = call.data.get("product_name")
        quantity = call.data.get("quantity", 1)

        # Get the first available API instance
        # In multi-instance setups, user should specify entry_id
        if not hass.data.get(DOMAIN):
            _LOGGER.error("No Tesco integration configured")
            return

        entry_id = list(hass.data[DOMAIN].keys())[0]
        api = hass.data[DOMAIN][entry_id]["api"]

        # Search for product
        products = await api.async_search_products(product_name)
        if products:
            await api.async_add_to_basket(products[0]["id"], quantity)
            _LOGGER.info("Added item to basket")
        else:
            _LOGGER.warning("Product not found")

    async def handle_ingest_receipt(call: ServiceCall) -> None:
        """Handle receipt ingestion service."""
        items = call.data.get("items", [])

        if not items:
            _LOGGER.warning("No items provided in receipt")
            return

        # Get inventory sensor from first entry
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            if isinstance(entry_data, dict) and "inventory_sensor" in entry_data:
                sensor = entry_data["inventory_sensor"]
                await sensor.async_add_items_from_receipt(items)
                _LOGGER.info("Added %d items to inventory", len(items))
                return

        _LOGGER.error("No inventory sensor found")

    async def handle_remove_from_inventory(call: ServiceCall) -> None:
        """Handle remove from inventory service."""
        product_id = call.data.get("product_id")
        quantity = call.data.get("quantity", 1)

        # Get inventory sensor from first entry
        for entry_id, entry_data in hass.data.get(DOMAIN, {}).items():
            if isinstance(entry_data, dict) and "inventory_sensor" in entry_data:
                sensor = entry_data["inventory_sensor"]
                await sensor.async_remove_item(product_id, quantity)
                _LOGGER.info("Removed item from inventory")
                return

        _LOGGER.error("No inventory sensor found")

    async def handle_search_products(call: ServiceCall) -> None:
        """Handle product search service."""
        query = call.data.get("query")

        if not hass.data.get(DOMAIN):
            _LOGGER.error("No Tesco integration configured")
            return

        entry_id = list(hass.data[DOMAIN].keys())[0]
        api = hass.data[DOMAIN][entry_id]["api"]
        products = await api.async_search_products(query)

        _LOGGER.info("Found %d products", len(products))

        # Store results for potential retrieval
        hass.data[DOMAIN]["last_search_results"] = products

    # Register services (only once globally)
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_TO_BASKET,
        handle_add_to_basket,
        schema=vol.Schema(
            {
                vol.Required("product_name"): cv.string,
                vol.Optional("quantity", default=1): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_INGEST_RECEIPT,
        handle_ingest_receipt,
        schema=vol.Schema(
            {
                vol.Required("items"): [
                    {
                        vol.Required("name"): cv.string,
                        vol.Optional("id"): cv.string,
                        vol.Optional("quantity", default=1): cv.positive_int,
                        vol.Optional("unit", default="item"): cv.string,
                    }
                ]
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_REMOVE_FROM_INVENTORY,
        handle_remove_from_inventory,
        schema=vol.Schema(
            {
                vol.Required("product_id"): cv.string,
                vol.Optional("quantity", default=1): cv.positive_int,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH_PRODUCTS,
        handle_search_products,
        schema=vol.Schema({vol.Required("query"): cv.string}),
    )

    SERVICES_REGISTERED = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Close API session to prevent resource leak
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        api = hass.data[DOMAIN][entry.entry_id]["api"]
        await api.async_close()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    # Unregister services if this was the last entry
    if not hass.data.get(DOMAIN):
        global SERVICES_REGISTERED
        hass.services.async_remove(DOMAIN, SERVICE_ADD_TO_BASKET)
        hass.services.async_remove(DOMAIN, SERVICE_INGEST_RECEIPT)
        hass.services.async_remove(DOMAIN, SERVICE_REMOVE_FROM_INVENTORY)
        hass.services.async_remove(DOMAIN, SERVICE_SEARCH_PRODUCTS)
        SERVICES_REGISTERED = False

    return unload_ok
