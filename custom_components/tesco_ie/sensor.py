"""Sensor platform for Tesco Ireland integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 2  # Incremented for delivery metadata support
STORAGE_KEY = "tesco_ie_inventory"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tesco sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # Create inventory sensor with persistence
    inventory_sensor = TescoInventorySensor(hass, coordinator, entry)
    await inventory_sensor.async_load_inventory()

    sensors = [
        TescoClubcardSensor(coordinator, entry),
        inventory_sensor,
        TescoNextDeliverySensor(coordinator, entry),
        TescoDiagnosticSensor(coordinator, entry),
    ]

    async_add_entities(sensors)

    # Store sensor reference for service access
    hass.data[DOMAIN][entry.entry_id]["inventory_sensor"] = inventory_sensor


class TescoBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Tesco sensors."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self._entry.entry_id)},
            "name": "Tesco Ireland",
            "manufacturer": "Tesco",
            "model": "Tesco IE Account",
        }


class TescoClubcardSensor(TescoBaseSensor):
    """Sensor for Clubcard points."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the Clubcard sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_clubcard_points"
        self._attr_name = "Clubcard Points"
        self._attr_icon = "mdi:credit-card-outline"
        self._attr_state_class = SensorStateClass.TOTAL

    @property
    def native_value(self) -> int:
        """Return the state of the sensor."""
        if self.coordinator.data:
            return self.coordinator.data.get("clubcard_points", 0)
        return 0


class TescoInventorySensor(TescoBaseSensor):
    """Sensor for home inventory tracking with persistence."""

    def __init__(self, hass: HomeAssistant, coordinator, entry: ConfigEntry) -> None:
        """Initialize the inventory sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_inventory"
        self._attr_name = "Home Inventory"
        self._attr_icon = "mdi:package-variant"
        self._inventory: dict[str, dict[str, Any]] = {}
        self._hass = hass
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY}_{entry.entry_id}",
        )

    async def async_load_inventory(self) -> None:
        """Load inventory from persistent storage with migration support."""
        try:
            data = await self._store.async_load()
            if data is not None:
                # Check storage version and migrate if needed
                stored_version = data.get("version", 1)
                if stored_version < STORAGE_VERSION:
                    _LOGGER.info(
                        "Migrating inventory storage from version %d to %d",
                        stored_version,
                        STORAGE_VERSION,
                    )
                    data = await self._migrate_storage(data, stored_version)

                self._inventory = data.get("inventory", {})
                _LOGGER.debug(
                    "Loaded %d items from inventory storage", len(self._inventory)
                )
        except Exception as err:
            _LOGGER.error("Failed to load inventory: %s", err)
            self._inventory = {}

    async def _migrate_storage(
        self, data: dict[str, Any], from_version: int
    ) -> dict[str, Any]:
        """Migrate storage from old version to current version.

        Args:
            data: Current storage data
            from_version: Version to migrate from

        Returns:
            Migrated storage data
        """
        inventory = data.get("inventory", {})

        if from_version == 1:
            # Migrate from version 1 to version 2
            # Add delivery metadata to existing items
            _LOGGER.debug("Migrating from version 1 to version 2")
            for product_id, item_data in inventory.items():
                if "deliveries" not in item_data:
                    # Convert old format to new format with delivery tracking
                    quantity = item_data.get("quantity", 0)
                    item_data["deliveries"] = [
                        {
                            "batch_id": "migrated",
                            "quantity": quantity,
                            "delivered_at": item_data.get(
                                "added", datetime.now().isoformat()
                            ),
                            "order_number": None,
                        }
                    ]
                    # Keep total quantity for backwards compatibility
                    item_data["quantity"] = quantity

        data["version"] = STORAGE_VERSION
        data["inventory"] = inventory
        return data

    async def async_save_inventory(self) -> None:
        """Save inventory to persistent storage with version."""
        try:
            await self._store.async_save(
                {
                    "version": STORAGE_VERSION,
                    "inventory": self._inventory,
                    "last_saved": datetime.now().isoformat(),
                }
            )
            _LOGGER.debug("Saved inventory to storage (version %d)", STORAGE_VERSION)
        except Exception as err:
            _LOGGER.error("Failed to save inventory: %s", err)

    @property
    def native_value(self) -> int:
        """Return the number of items in inventory."""
        return len(self._inventory)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        return {
            "items": self._inventory,
            "last_updated": datetime.now().isoformat(),
            "total_items": len(self._inventory),
        }

    async def async_add_items_from_receipt(
        self, items: list[dict[str, Any]], order_number: str | None = None
    ) -> None:
        """Add items from a delivery receipt with delivery metadata.

        Args:
            items: List of items from the receipt
            order_number: Optional order number for tracking
        """
        _LOGGER.info("Adding %d items from receipt to inventory", len(items))
        delivered_at = datetime.now().isoformat()
        batch_id = f"delivery_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        for item in items:
            product_id = item.get("id", item.get("name", "unknown"))
            quantity = item.get("quantity", 1)

            if product_id in self._inventory:
                # Add new delivery batch to existing item
                self._inventory[product_id]["quantity"] += quantity
                self._inventory[product_id]["last_added"] = delivered_at
                self._inventory[product_id]["deliveries"].append(
                    {
                        "batch_id": batch_id,
                        "quantity": quantity,
                        "delivered_at": delivered_at,
                        "order_number": order_number,
                    }
                )
            else:
                # Create new item with delivery metadata
                self._inventory[product_id] = {
                    "name": item.get("name", "Unknown"),
                    "quantity": quantity,
                    "unit": item.get("unit", "item"),
                    "added": delivered_at,
                    "last_added": delivered_at,
                    "deliveries": [
                        {
                            "batch_id": batch_id,
                            "quantity": quantity,
                            "delivered_at": delivered_at,
                            "order_number": order_number,
                        }
                    ],
                }

        await self.async_save_inventory()
        self.async_write_ha_state()

    async def async_remove_item(self, product_id: str, quantity: int = 1) -> None:
        """Remove item from inventory using FIFO (First In, First Out).

        Removes items from oldest delivery batches first.

        Args:
            product_id: Product identifier
            quantity: Quantity to remove
        """
        if product_id in self._inventory:
            remaining_to_remove = quantity
            item = self._inventory[product_id]
            deliveries = item.get("deliveries", [])

            # Remove from deliveries using FIFO
            updated_deliveries = []
            for delivery in deliveries:
                if remaining_to_remove <= 0:
                    # Keep remaining deliveries
                    updated_deliveries.append(delivery)
                elif delivery["quantity"] <= remaining_to_remove:
                    # Remove entire delivery batch
                    remaining_to_remove -= delivery["quantity"]
                    _LOGGER.debug(
                        "Removed entire batch %s (%d items)",
                        delivery["batch_id"],
                        delivery["quantity"],
                    )
                else:
                    # Partially remove from this batch
                    delivery["quantity"] -= remaining_to_remove
                    _LOGGER.debug(
                        "Removed %d items from batch %s",
                        remaining_to_remove,
                        delivery["batch_id"],
                    )
                    remaining_to_remove = 0
                    updated_deliveries.append(delivery)

            # Update total quantity
            item["quantity"] -= quantity
            item["deliveries"] = updated_deliveries

            if item["quantity"] <= 0:
                del self._inventory[product_id]
                _LOGGER.debug("Removed product from inventory completely")
            else:
                _LOGGER.debug(
                    "Reduced quantity in inventory to %d (across %d batches)",
                    item["quantity"],
                    len(updated_deliveries),
                )

            await self.async_save_inventory()
            self.async_write_ha_state()
        else:
            _LOGGER.warning("Product %s not found in inventory", product_id)

    async def async_will_remove_from_hass(self) -> None:
        """Run when entity will be removed from hass."""
        # Save one last time before removal
        await self.async_save_inventory()


class TescoNextDeliverySensor(TescoBaseSensor):
    """Sensor for next delivery information."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the delivery sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_delivery"
        self._attr_name = "Next Delivery"
        self._attr_icon = "mdi:truck-delivery"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        """Return the state of the sensor."""
        if self.coordinator.data and self.coordinator.data.get("next_delivery"):
            return self.coordinator.data["next_delivery"]
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if self.coordinator.data and self.coordinator.data.get("next_delivery"):
            return {
                "delivery_slot": self.coordinator.data.get("delivery_slot"),
                "order_number": self.coordinator.data.get("order_number"),
            }
        return {}


class TescoDiagnosticSensor(TescoBaseSensor):
    """Diagnostic sensor for monitoring integration health."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the diagnostic sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_diagnostic"
        self._attr_name = "Integration Health"
        self._attr_icon = "mdi:heart-pulse"
        self._attr_entity_category = "diagnostic"

    @property
    def native_value(self) -> str:
        """Return the health status."""
        if not self.coordinator.last_update_success:
            return "error"
        if self.coordinator.data:
            return "healthy"
        return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return diagnostic attributes."""
        attrs = {
            "last_update_success": self.coordinator.last_update_success,
            "last_update_time": (
                self.coordinator.last_update_success_time.isoformat()
                if self.coordinator.last_update_success_time
                else None
            ),
        }

        if self.coordinator.data:
            # Track if selectors are finding data
            attrs["clubcard_points_found"] = (
                self.coordinator.data.get("clubcard_points", 0) > 0
            )
            attrs["basket_items_found"] = (
                len(self.coordinator.data.get("basket_items", [])) > 0
            )
            attrs["delivery_info_found"] = (
                self.coordinator.data.get("next_delivery") is not None
            )

        # Get API session info from hass.data
        entry_data = self.hass.data.get("tesco_ie", {}).get(self._entry.entry_id, {})
        if "api" in entry_data:
            api = entry_data["api"]
            attrs["session_active"] = api.is_logged_in
            attrs["has_csrf_token"] = api.has_csrf_token

        if self.coordinator.last_exception:
            attrs["last_error"] = str(self.coordinator.last_exception)

        return attrs
