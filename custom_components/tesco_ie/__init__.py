"""The Tesco Ireland integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

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


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tesco Ireland from a config entry."""
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]

    api = TescoAPI(email, password)

    try:
        await api.async_login()
    except Exception as err:
        _LOGGER.error("Failed to authenticate with Tesco: %s", err)
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

    # Register services
    await async_setup_services(hass, entry)

    return True


async def async_setup_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Set up services for Tesco integration."""

    async def handle_add_to_basket(call: ServiceCall) -> None:
        """Handle add to basket service."""
        product_name = call.data.get("product_name")
        quantity = call.data.get("quantity", 1)

        api = hass.data[DOMAIN][entry.entry_id]["api"]

        # Search for product
        products = await api.async_search_products(product_name)
        if products:
            await api.async_add_to_basket(products[0]["id"], quantity)
            _LOGGER.info("Added %s (x%d) to basket", product_name, quantity)
        else:
            _LOGGER.warning("Product not found: %s", product_name)

    async def handle_ingest_receipt(call: ServiceCall) -> None:
        """Handle receipt ingestion service."""
        items = call.data.get("items", [])

        # Get the inventory sensor
        entity_id = f"sensor.tesco_ie_inventory"
        states = hass.states.get(entity_id)

        if states is None:
            _LOGGER.error("Inventory sensor not found")
            return

        # Find the sensor entity
        for entry_data in hass.data[DOMAIN].values():
            coordinator = entry_data.get("coordinator")
            if coordinator:
                # Add items to inventory sensor
                # Note: This is a simplified approach
                # In production, you'd want to properly access the sensor entity
                _LOGGER.info("Ingesting %d items from receipt", len(items))
                break

    async def handle_remove_from_inventory(call: ServiceCall) -> None:
        """Handle remove from inventory service."""
        product_id = call.data.get("product_id")
        quantity = call.data.get("quantity", 1)

        _LOGGER.info("Removing %s (x%d) from inventory", product_id, quantity)

    async def handle_search_products(call: ServiceCall) -> None:
        """Handle product search service."""
        query = call.data.get("query")

        api = hass.data[DOMAIN][entry.entry_id]["api"]
        products = await api.async_search_products(query)

        _LOGGER.info("Found %d products for query: %s", len(products), query)
        return products

    # Register services
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


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
