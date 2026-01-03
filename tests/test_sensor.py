"""Tests for Tesco Ireland sensors."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from custom_components.tesco_ie.const import DOMAIN
from custom_components.tesco_ie.sensor import (
    TescoClubcardSensor,
    TescoInventorySensor,
    TescoNextDeliverySensor,
)


@pytest.fixture
def mock_coordinator():
    """Mock coordinator."""
    coordinator = MagicMock(spec=DataUpdateCoordinator)
    coordinator.data = {
        "clubcard_points": 250,
        "next_delivery": datetime(2024, 1, 15, 10, 0),
        "delivery_slot": "10:00 - 12:00",
        "order_number": "123456",
        "basket_items": [],
    }
    return coordinator


@pytest.fixture
def mock_entry():
    """Mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    return entry


@pytest.fixture
def mock_hass():
    """Mock Home Assistant instance."""
    return MagicMock(spec=HomeAssistant)


def test_clubcard_sensor_initialization(mock_coordinator, mock_entry):
    """Test Clubcard sensor initialization."""
    sensor = TescoClubcardSensor(mock_coordinator, mock_entry)

    assert sensor._attr_name == "Clubcard Points"
    assert sensor._attr_icon == "mdi:credit-card-outline"
    assert sensor._attr_unique_id == f"{mock_entry.entry_id}_clubcard_points"


def test_clubcard_sensor_value(mock_coordinator, mock_entry):
    """Test Clubcard sensor value."""
    sensor = TescoClubcardSensor(mock_coordinator, mock_entry)

    assert sensor.native_value == 250


def test_clubcard_sensor_no_data(mock_entry):
    """Test Clubcard sensor with no coordinator data."""
    coordinator = MagicMock(spec=DataUpdateCoordinator)
    coordinator.data = None

    sensor = TescoClubcardSensor(coordinator, mock_entry)

    assert sensor.native_value == 0


def test_inventory_sensor_initialization(mock_hass, mock_coordinator, mock_entry):
    """Test inventory sensor initialization."""
    sensor = TescoInventorySensor(mock_hass, mock_coordinator, mock_entry)

    assert sensor._attr_name == "Home Inventory"
    assert sensor._attr_icon == "mdi:package-variant"
    assert sensor._attr_unique_id == f"{mock_entry.entry_id}_inventory"
    assert sensor._inventory == {}


def test_inventory_sensor_value(mock_hass, mock_coordinator, mock_entry):
    """Test inventory sensor value."""
    sensor = TescoInventorySensor(mock_hass, mock_coordinator, mock_entry)

    assert sensor.native_value == 0  # Empty inventory


@pytest.mark.asyncio
async def test_inventory_add_items(mock_hass, mock_coordinator, mock_entry):
    """Test adding items to inventory."""
    sensor = TescoInventorySensor(mock_hass, mock_coordinator, mock_entry)
    sensor.hass = mock_hass  # Set hass attribute for entity

    items = [
        {"id": "milk_2l", "name": "Milk 2L", "quantity": 2, "unit": "liters"},
        {"name": "Bread", "quantity": 1, "unit": "loaf"},
    ]

    await sensor.async_add_items_from_receipt(items)

    assert sensor.native_value == 2  # Two unique items
    assert "milk_2l" in sensor._inventory
    assert sensor._inventory["milk_2l"]["quantity"] == 2
    assert "Bread" in sensor._inventory


@pytest.mark.asyncio
async def test_inventory_add_duplicate_items(mock_hass, mock_coordinator, mock_entry):
    """Test adding duplicate items increases quantity."""
    sensor = TescoInventorySensor(mock_hass, mock_coordinator, mock_entry)
    sensor.hass = mock_hass  # Set hass attribute for entity

    # Add first batch
    items1 = [{"id": "milk_2l", "name": "Milk 2L", "quantity": 2}]
    await sensor.async_add_items_from_receipt(items1)

    assert sensor._inventory["milk_2l"]["quantity"] == 2

    # Add second batch
    items2 = [{"id": "milk_2l", "name": "Milk 2L", "quantity": 1}]
    await sensor.async_add_items_from_receipt(items2)

    assert sensor._inventory["milk_2l"]["quantity"] == 3
    assert sensor.native_value == 1  # Still one unique item


@pytest.mark.asyncio
async def test_inventory_remove_item(mock_hass, mock_coordinator, mock_entry):
    """Test removing items from inventory."""
    sensor = TescoInventorySensor(mock_hass, mock_coordinator, mock_entry)
    sensor.hass = mock_hass  # Set hass attribute for entity

    # Add items first
    items = [{"id": "milk_2l", "name": "Milk 2L", "quantity": 3}]
    await sensor.async_add_items_from_receipt(items)

    # Remove one
    await sensor.async_remove_item("milk_2l", 1)
    assert sensor._inventory["milk_2l"]["quantity"] == 2

    # Remove remaining
    await sensor.async_remove_item("milk_2l", 2)
    assert "milk_2l" not in sensor._inventory


@pytest.mark.asyncio
async def test_inventory_attributes(mock_hass, mock_coordinator, mock_entry):
    """Test inventory sensor attributes."""
    sensor = TescoInventorySensor(mock_hass, mock_coordinator, mock_entry)
    sensor.hass = mock_hass  # Set hass attribute for entity

    items = [{"id": "milk_2l", "name": "Milk 2L", "quantity": 2}]
    await sensor.async_add_items_from_receipt(items)

    attrs = sensor.extra_state_attributes

    assert "items" in attrs
    assert "last_updated" in attrs
    assert attrs["items"]["milk_2l"]["quantity"] == 2


def test_delivery_sensor_initialization(mock_coordinator, mock_entry):
    """Test delivery sensor initialization."""
    sensor = TescoNextDeliverySensor(mock_coordinator, mock_entry)

    assert sensor._attr_name == "Next Delivery"
    assert sensor._attr_icon == "mdi:truck-delivery"
    assert sensor._attr_unique_id == f"{mock_entry.entry_id}_next_delivery"


def test_delivery_sensor_value(mock_coordinator, mock_entry):
    """Test delivery sensor value."""
    sensor = TescoNextDeliverySensor(mock_coordinator, mock_entry)

    expected_date = datetime(2024, 1, 15, 10, 0)
    assert sensor.native_value == expected_date


def test_delivery_sensor_no_delivery(mock_entry):
    """Test delivery sensor with no upcoming delivery."""
    coordinator = MagicMock(spec=DataUpdateCoordinator)
    coordinator.data = {"next_delivery": None}

    sensor = TescoNextDeliverySensor(coordinator, mock_entry)

    assert sensor.native_value is None


def test_delivery_sensor_attributes(mock_coordinator, mock_entry):
    """Test delivery sensor attributes."""
    sensor = TescoNextDeliverySensor(mock_coordinator, mock_entry)

    attrs = sensor.extra_state_attributes

    assert attrs["delivery_slot"] == "10:00 - 12:00"
    assert attrs["order_number"] == "123456"


def test_sensor_device_info(mock_coordinator, mock_entry):
    """Test sensor device info."""
    sensor = TescoClubcardSensor(mock_coordinator, mock_entry)

    device_info = sensor.device_info

    assert device_info["name"] == "Tesco Ireland"
    assert device_info["manufacturer"] == "Tesco"
    assert (DOMAIN, mock_entry.entry_id) in device_info["identifiers"]
