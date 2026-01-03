"""Sensor platform for Tesco Ireland integration."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Tesco sensors from a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    sensors = [
        TescoClubcardSensor(coordinator, entry),
        TescoInventorySensor(coordinator, entry),
        TescoNextDeliverySensor(coordinator, entry),
    ]

    async_add_entities(sensors)


class TescoBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Tesco sensors."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_has_entity_name = True

    @property
    def device_info(self):
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
    """Sensor for home inventory tracking."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the inventory sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_inventory"
        self._attr_name = "Home Inventory"
        self._attr_icon = "mdi:package-variant"
        self._inventory: dict[str, dict[str, Any]] = {}

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
        }

    def add_items_from_receipt(self, items: list[dict[str, Any]]) -> None:
        """Add items from a delivery receipt."""
        _LOGGER.info("Adding %d items from receipt to inventory", len(items))

        for item in items:
            product_id = item.get("id", item.get("name", "unknown"))
            quantity = item.get("quantity", 1)

            if product_id in self._inventory:
                self._inventory[product_id]["quantity"] += quantity
                self._inventory[product_id]["last_added"] = datetime.now().isoformat()
            else:
                self._inventory[product_id] = {
                    "name": item.get("name", "Unknown"),
                    "quantity": quantity,
                    "unit": item.get("unit", "item"),
                    "added": datetime.now().isoformat(),
                    "last_added": datetime.now().isoformat(),
                }

        self.async_write_ha_state()

    def remove_item(self, product_id: str, quantity: int = 1) -> None:
        """Remove item from inventory."""
        if product_id in self._inventory:
            self._inventory[product_id]["quantity"] -= quantity
            if self._inventory[product_id]["quantity"] <= 0:
                del self._inventory[product_id]
            self.async_write_ha_state()


class TescoNextDeliverySensor(TescoBaseSensor):
    """Sensor for next delivery information."""

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        """Initialize the delivery sensor."""
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_next_delivery"
        self._attr_name = "Next Delivery"
        self._attr_icon = "mdi:truck-delivery"
        self._attr_device_class = "timestamp"

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
