"""Shopping list platform for Tesco Ireland integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tesco shopping list from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    api = hass.data[DOMAIN][entry.entry_id]["api"]

    # Register the shopping list component
    async_add_entities([TescoShoppingList(coordinator, api)])


class TescoShoppingList:
    """Tesco shopping list implementation."""

    def __init__(self, coordinator, api) -> None:
        """Initialize the shopping list."""
        self._coordinator = coordinator
        self._api = api
        self._items: list[dict[str, Any]] = []

    @property
    def items(self) -> list[dict[str, Any]]:
        """Return shopping list items."""
        return self._items

    async def async_add_item(self, name: str) -> None:
        """Add item to the list and Tesco basket."""
        _LOGGER.info("Adding item to shopping list: %s", name)

        # Search for the product
        products = await self._api.async_search_products(name)

        if products:
            # Add first matching product to basket
            product = products[0]
            await self._api.async_add_to_basket(product["id"])

            # Add to local list
            self._items.append(
                {
                    "name": name,
                    "id": product["id"],
                    "complete": False,
                }
            )
        else:
            # Add to local list even if not found in Tesco
            self._items.append(
                {
                    "name": name,
                    "id": None,
                    "complete": False,
                }
            )

    async def async_update_item(self, item_id: str, updates: dict) -> None:
        """Update an item."""
        for item in self._items:
            if item.get("id") == item_id:
                item.update(updates)
                break

    async def async_remove_item(self, item_id: str) -> None:
        """Remove an item."""
        self._items = [item for item in self._items if item.get("id") != item_id]

    async def async_clear_completed(self) -> None:
        """Clear completed items."""
        self._items = [item for item in self._items if not item.get("complete")]
