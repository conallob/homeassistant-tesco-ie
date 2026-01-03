# Tesco Ireland Home Assistant Integration

A Home Assistant custom integration for Tesco Ireland that enables smart home automation with your Tesco account.

## ⚠️ IMPORTANT: Placeholder Implementation Warning

**This integration currently uses placeholder HTML selectors and has NOT been tested against the real Tesco Ireland website.** The web scraping implementation uses generic CSS selectors and regex patterns that may not match the actual Tesco.ie website structure.

**Before using this integration in production:**
1. Test all functionality against the real Tesco.ie website
2. Update HTML selectors in `tesco_api.py` to match actual page structure
3. Verify authentication flow and CSRF token extraction
4. Validate product search, basket operations, and data parsing
5. Test rate limiting to avoid being blocked by anti-bot protection

**The current implementation is a framework that requires real-world testing and selector updates.**

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

This integration uses web scraping to interact with Tesco Ireland's website. The implementation includes:

- **Session Management**: Persistent cookie jar and session handling
- **CSRF Token Handling**: Automatic extraction and submission of CSRF tokens
- **Rate Limiting**: Built-in delays to avoid triggering anti-bot protection
- **Browser Emulation**: Proper user agent and headers to mimic real browser behavior

### Implementation Details

The `tesco_api.py` module implements web scraping with:

- **Authentication**: Form-based login with email/password
- **Cookie Persistence**: Session cookies maintained across requests
- **HTML Parsing**: BeautifulSoup4 and lxml for parsing page content
- **Error Handling**: Comprehensive error detection and logging
- **Flexible Selectors**: Regex-based element matching to handle site changes

### Important Notes

- **⚠️ PLACEHOLDER SELECTORS**: All HTML selectors in `tesco_api.py` are placeholders (`.selector-*`, `#element-*`). These MUST be replaced with actual Tesco.ie selectors before the integration will work.
- **⚠️ UNTESTED**: This integration has not been tested against the real Tesco Ireland website. All functionality needs real-world validation.
- **Site Changes**: Tesco may update their website structure, requiring selector updates
- **Anti-Bot Protection**: Tesco uses bot detection; excessive requests may be blocked
- **Rate Limiting**: The integration implements 1-second delays between requests
- **Login Required**: All features require valid Tesco Ireland credentials
- **Receipt Parsing**: Currently requires manual service calls; automatic email parsing not yet implemented

### Known Limitations

- Authentication flow may differ from the implemented placeholder
- Product search selectors are generic and need real page analysis
- Basket management endpoints are assumed and not verified
- Clubcard points and delivery information selectors are placeholders
- CSRF token extraction logic may need adjustment for actual site

## Testing

This integration includes a comprehensive test suite to ensure reliability and maintainability.

### Running Tests Locally

```bash
# Install test dependencies
pip install -r requirements-test.txt

# Run all tests
pytest

# Run tests with coverage
pytest --cov=custom_components.tesco_ie --cov-report=html

# Run specific test file
pytest tests/test_tesco_api.py

# Run tests in verbose mode
pytest -v
```

### Test Coverage

The test suite includes:

- **API Client Tests** (18 tests): Session management, authentication, CSRF tokens, data parsing, rate limiting
- **Config Flow Tests** (5 tests): Configuration UI, validation, error handling
- **Sensor Tests** (13 tests): All sensor types, inventory management, attributes
- **Integration Tests** (4 tests): Setup, teardown, coordinator updates

### Continuous Integration

All pull requests automatically run:

- **Unit tests** on Python 3.11 and 3.12
- **Code quality checks** with ruff, black, isort, and mypy
- **Integration validation** for manifest and required files
- **Coverage reporting** via Codecov

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

Before submitting:
1. Run the test suite: `pytest`
2. Check code formatting: `black custom_components/`
3. Run linting: `ruff check custom_components/`
4. Ensure tests pass in CI

## License

This project is licensed under the terms included in the LICENSE file.

## Disclaimer

This integration is not affiliated with, endorsed by, or connected to Tesco. Use at your own risk.
