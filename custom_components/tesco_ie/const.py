"""Constants for the Tesco Ireland integration."""
from datetime import timedelta

DOMAIN = "tesco_ie"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"

# Update interval for sensors
SCAN_INTERVAL = timedelta(minutes=30)

# Sensor types
SENSOR_CLUBCARD_POINTS = "clubcard_points"
SENSOR_NEXT_DELIVERY = "next_delivery"
SENSOR_DELIVERY_SLOTS = "delivery_slots"

# Services
SERVICE_ADD_TO_BASKET = "add_to_basket"
SERVICE_INGEST_RECEIPT = "ingest_receipt"
SERVICE_REMOVE_FROM_INVENTORY = "remove_from_inventory"
SERVICE_SEARCH_PRODUCTS = "search_products"
