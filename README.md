# Tesco Ireland Home Assistant Integration

A Home Assistant custom integration for Tesco Ireland that enables smart home automation with your Tesco account.

## Features

- **Shopping Basket Management**: Add items to your Tesco shopping basket directly from Home Assistant
- **Home Inventory Tracking**: Track items delivered to your home by ingesting delivery receipts
- **Clubcard Points**: Monitor your Clubcard points balance
- **Delivery Information**: Track your next delivery date and time
- **Product Search**: Search for Tesco products via services

## Installation

### HACS (Recommended)

1. Add this repository to HACS as a custom repository
2. Search for "Tesco Ireland" in HACS
3. Click Install
4. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/tesco_ie` folder to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to Settings > Devices & Services
2. Click "+ Add Integration"
3. Search for "Tesco Ireland"
4. Enter your Tesco.ie email and password
5. Click Submit

## Entities

After configuration, the following entities will be created:

- `sensor.tesco_ie_clubcard_points` - Your current Clubcard points balance
- `sensor.tesco_ie_home_inventory` - Number of items in your home inventory (with detailed attributes)
- `sensor.tesco_ie_next_delivery` - Date and time of your next delivery

## Services

### tesco_ie.add_to_basket

Add a product to your Tesco shopping basket.

```yaml
service: tesco_ie.add_to_basket
data:
  product_name: "Milk"
  quantity: 2
```

### tesco_ie.ingest_receipt

Add items from a delivery receipt to your home inventory.

```yaml
service: tesco_ie.ingest_receipt
data:
  items:
    - name: "Milk"
      id: "12345"
      quantity: 2
      unit: "liters"
    - name: "Bread"
      quantity: 1
      unit: "loaf"
```

### tesco_ie.remove_from_inventory

Remove items from your home inventory when consumed.

```yaml
service: tesco_ie.remove_from_inventory
data:
  product_id: "milk_2l"
  quantity: 1
```

### tesco_ie.search_products

Search for products in Tesco's catalog.

```yaml
service: tesco_ie.search_products
data:
  query: "organic milk"
```

## Example Automations

### Automatic Receipt Ingestion

```yaml
automation:
  - alias: "Ingest Tesco Delivery Receipt"
    trigger:
      - platform: state
        entity_id: sensor.tesco_ie_next_delivery
        to: "delivered"
    action:
      - service: tesco_ie.ingest_receipt
        data:
          items: "{{ trigger.to_state.attributes.items }}"
```

### Low Stock Alert

```yaml
automation:
  - alias: "Low Milk Stock Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.tesco_ie_home_inventory
        value_template: "{{ state.attributes.items.milk_2l.quantity }}"
        below: 1
    action:
      - service: tesco_ie.add_to_basket
        data:
          product_name: "Milk 2L"
          quantity: 2
```

### Shopping List Integration

```yaml
automation:
  - alias: "Add Shopping List Items to Tesco Basket"
    trigger:
      - platform: event
        event_type: shopping_list_updated
    action:
      - service: tesco_ie.add_to_basket
        data:
          product_name: "{{ trigger.event.data.item }}"
```

## Development Status

This integration is currently in development. The Tesco API client (`tesco_api.py`) contains placeholder implementations that need to be replaced with actual API calls or web scraping logic to interact with Tesco Ireland's services.

### Implementation Notes

- Authentication with Tesco Ireland requires reverse engineering their API or implementing web scraping
- Product search and basket management will need actual API endpoints or DOM manipulation
- Receipt parsing may require OCR or structured data from Tesco's order confirmation emails

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the terms included in the LICENSE file.

## Disclaimer

This integration is not affiliated with, endorsed by, or connected to Tesco. Use at your own risk.
