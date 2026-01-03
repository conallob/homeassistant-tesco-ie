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
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_EMAIL,
    CONF_PASSWORD,
    DOMAIN,
    SERVICE_ADD_TO_BASKET,
    SERVICE_INGEST_RECEIPT,
    SERVICE_REMOVE_FROM_INVENTORY,
    SERVICE_SEARCH_PRODUCTS,
)
from .tesco_api import TescoAPI, TescoAPIError, TescoAuthError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

# Key for tracking service registration in hass.data
SERVICES_KEY = "services_registered"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Tesco Ireland from a config entry."""
    # Note: Home Assistant encrypts config entry data automatically
    # Passwords are not stored in plaintext in storage
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]

    api = TescoAPI(email, password)

    try:
        await api.async_login()
    except (TescoAuthError, TescoAPIError) as err:
        _LOGGER.error("Failed to authenticate with Tesco")
        raise ConfigEntryAuthFailed from err

    async def async_update_data():
        """Fetch data from Tesco API."""
        try:
            return await api.async_get_data()
        except TescoAuthError:
            # Auth failures during updates should trigger re-login
            _LOGGER.warning("Authentication expired, attempting re-login")
            try:
                await api.async_login()
                return await api.async_get_data()
            except (TescoAuthError, TescoAPIError) as retry_err:
                raise UpdateFailed(
                    f"Re-authentication failed: {retry_err}"
                ) from retry_err
        except TescoAPIError as err:
            raise UpdateFailed(f"API error: {err}") from err
        except Exception as err:
            _LOGGER.exception("Unexpected error fetching data")
            raise UpdateFailed(f"Unexpected error: {err}") from err

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
    # Track service registration in hass.data instead of global variable
    if hass.data[DOMAIN].get(SERVICES_KEY):
        return

    async def handle_add_to_basket(call: ServiceCall) -> None:
        """Handle add to basket service."""
        product_name = call.data.get("product_name")
        quantity = call.data.get("quantity", 1)
        entry_id = call.data.get("entry_id")

        # Get API instance - use specified entry_id or first available
        if entry_id:
            if entry_id not in hass.data.get(DOMAIN, {}):
                _LOGGER.error("Config entry %s not found", entry_id)
                return
            api = hass.data[DOMAIN][entry_id]["api"]
        else:
            # Get first available entry
            entries = {
                k: v
                for k, v in hass.data.get(DOMAIN, {}).items()
                if isinstance(v, dict) and "api" in v
            }
            if not entries:
                _LOGGER.error("No Tesco integration configured")
                return
            api = next(iter(entries.values()))["api"]

        # Search for product
        try:
            products = await api.async_search_products(product_name)
            if products:
                result = await api.async_add_to_basket(products[0]["id"], quantity)
                if result["success"]:
                    _LOGGER.info("Added item to basket")
                else:
                    # Create persistent notification for failure
                    hass.components.persistent_notification.async_create(
                        f"Failed to add '{product_name}' to basket: {result['message']}",
                        title="Tesco Basket Error",
                        notification_id=f"tesco_basket_error_{entry_id or 'default'}",
                    )
                    _LOGGER.error("Failed to add to basket: %s", result["message"])
            else:
                # Create persistent notification for product not found
                hass.components.persistent_notification.async_create(
                    f"Product '{product_name}' not found in search results. "
                    "Please verify the product name.",
                    title="Tesco Product Not Found",
                    notification_id=f"tesco_product_not_found_{entry_id or 'default'}",
                )
                _LOGGER.warning("Product not found: %s", product_name)
        except (TescoAuthError, TescoAPIError) as err:
            # Create persistent notification for API errors
            hass.components.persistent_notification.async_create(
                f"Error adding '{product_name}' to basket: {err}",
                title="Tesco API Error",
                notification_id=f"tesco_api_error_{entry_id or 'default'}",
            )
            _LOGGER.error("Failed to add to basket: %s", err)

    async def handle_ingest_receipt(call: ServiceCall) -> None:
        """Handle receipt ingestion service."""
        items = call.data.get("items", [])
        entry_id = call.data.get("entry_id")

        if not items:
            _LOGGER.warning("No items provided in receipt")
            return

        # Validate item structure
        for item in items:
            if not isinstance(item, dict) or "name" not in item:
                _LOGGER.error("Invalid item structure: missing 'name' field")
                return

        # Get inventory sensor - use specified entry_id or first available
        if entry_id:
            if entry_id not in hass.data.get(DOMAIN, {}):
                _LOGGER.error("Config entry %s not found", entry_id)
                return
            entry_data = hass.data[DOMAIN][entry_id]
        else:
            # Get first available entry with inventory sensor
            entries = {
                k: v
                for k, v in hass.data.get(DOMAIN, {}).items()
                if isinstance(v, dict) and "inventory_sensor" in v
            }
            if not entries:
                _LOGGER.error("No inventory sensor found")
                return
            entry_data = next(iter(entries.values()))

        if "inventory_sensor" in entry_data:
            sensor = entry_data["inventory_sensor"]
            await sensor.async_add_items_from_receipt(items)
            _LOGGER.info("Added %d items to inventory", len(items))
        else:
            _LOGGER.error("No inventory sensor found")

    async def handle_remove_from_inventory(call: ServiceCall) -> None:
        """Handle remove from inventory service."""
        product_id = call.data.get("product_id")
        quantity = call.data.get("quantity", 1)
        entry_id = call.data.get("entry_id")

        # Get inventory sensor - use specified entry_id or first available
        if entry_id:
            if entry_id not in hass.data.get(DOMAIN, {}):
                _LOGGER.error("Config entry %s not found", entry_id)
                return
            entry_data = hass.data[DOMAIN][entry_id]
        else:
            # Get first available entry with inventory sensor
            entries = {
                k: v
                for k, v in hass.data.get(DOMAIN, {}).items()
                if isinstance(v, dict) and "inventory_sensor" in v
            }
            if not entries:
                _LOGGER.error("No inventory sensor found")
                return
            entry_data = next(iter(entries.values()))

        if "inventory_sensor" in entry_data:
            sensor = entry_data["inventory_sensor"]
            await sensor.async_remove_item(product_id, quantity)
            _LOGGER.info("Removed item from inventory")
        else:
            _LOGGER.error("No inventory sensor found")

    async def handle_search_products(call: ServiceCall) -> None:
        """Handle product search service."""
        query = call.data.get("query")
        entry_id = call.data.get("entry_id")

        # Get API instance - use specified entry_id or first available
        if entry_id:
            if entry_id not in hass.data.get(DOMAIN, {}):
                _LOGGER.error("Config entry %s not found", entry_id)
                return
            api = hass.data[DOMAIN][entry_id]["api"]
        else:
            # Get first available entry
            entries = {
                k: v
                for k, v in hass.data.get(DOMAIN, {}).items()
                if isinstance(v, dict) and "api" in v
            }
            if not entries:
                _LOGGER.error("No Tesco integration configured")
                return
            api = next(iter(entries.values()))["api"]

        try:
            products = await api.async_search_products(query)
            _LOGGER.info("Found %d products", len(products))
            # Store results for potential retrieval
            hass.data[DOMAIN]["last_search_results"] = products
        except (TescoAuthError, TescoAPIError) as err:
            _LOGGER.error("Failed to search products: %s", err)

    # Register services (only once globally)
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_TO_BASKET,
        handle_add_to_basket,
        schema=vol.Schema(
            {
                vol.Required("product_name"): cv.string,
                vol.Optional("quantity", default=1): cv.positive_int,
                vol.Optional("entry_id"): cv.string,
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
                ],
                vol.Optional("entry_id"): cv.string,
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
                vol.Optional("entry_id"): cv.string,
            }
        ),
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH_PRODUCTS,
        handle_search_products,
        schema=vol.Schema(
            {
                vol.Required("query"): cv.string,
                vol.Optional("entry_id"): cv.string,
            }
        ),
    )

    # Mark services as registered in hass.data (not global variable)
    hass.data[DOMAIN][SERVICES_KEY] = True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Close API session to prevent resource leak
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        api = hass.data[DOMAIN][entry.entry_id]["api"]
        await api.async_close()

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    # Unregister services if this was the last entry
    if not any(
        isinstance(v, dict) and "api" in v for v in hass.data.get(DOMAIN, {}).values()
    ):
        hass.services.async_remove(DOMAIN, SERVICE_ADD_TO_BASKET)
        hass.services.async_remove(DOMAIN, SERVICE_INGEST_RECEIPT)
        hass.services.async_remove(DOMAIN, SERVICE_REMOVE_FROM_INVENTORY)
        hass.services.async_remove(DOMAIN, SERVICE_SEARCH_PRODUCTS)
        hass.data[DOMAIN].pop(SERVICES_KEY, None)

    return unload_ok
