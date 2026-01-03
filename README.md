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

## Configuration

After installation, you can configure the integration behavior through the Home Assistant UI:

1. Go to **Settings** > **Devices & Services**
2. Find **Tesco Ireland** in the list
3. Click **Configure** (or the three dots menu → **Options**)
4. Adjust settings:
   - **Update Interval**: How often to fetch data (60-3600 seconds, default: 300)
   - **Timeout**: Request timeout (10-120 seconds, default: 30)
   - **Read Rate Limit**: Delay between read operations (0.5-10 seconds, default: 1.0)
   - **Write Rate Limit**: Delay between write operations (1.0-10 seconds, default: 2.0)

## Troubleshooting

### Integration Health Monitoring

The integration includes a diagnostic sensor (`sensor.tesco_ie_integration_health`) that monitors:

- **Session Status**: Whether the API session is active
- **Selector Success**: Whether data selectors are finding elements
- **Last Update**: Timestamp and success status of the last update
- **CSRF Token**: Whether authentication tokens are present

Check this sensor's attributes for diagnostic information when troubleshooting.

### Common Issues

#### Authentication Failures

**Symptom**: Integration shows "Authentication Failed" error

**Solutions**:
1. Verify your Tesco.ie credentials are correct
2. Check if Tesco.ie login page structure has changed
3. Enable debug logging to see detailed authentication flow
4. Check `sensor.tesco_ie_integration_health` attributes for session status

#### No Data Retrieved

**Symptom**: Sensors show 0 or no data

**Solutions**:
1. Check the diagnostic sensor attributes for selector success rates
2. Enable debug logging to see which selectors are failing
3. Inspect Tesco.ie HTML structure (see guide below)
4. Update selectors in `tesco_api.py` to match actual page structure

#### Rate Limiting / Blocked Requests

**Symptom**: HTTP 429 errors or integration stops working

**Solutions**:
1. Increase rate limit delays in configuration
2. Reduce update interval to fewer requests
3. Wait 24 hours before retrying (Tesco may have temporarily blocked your IP)
4. Consider using a VPN to change IP address

#### Integration Becomes Unresponsive

**Symptom**: Integration stops updating or becomes slow

**Solutions**:
1. Restart Home Assistant
2. Check Home Assistant logs for errors
3. Increase timeout setting if network is slow
4. Verify Tesco.ie website is accessible from your network

### Debugging

Enable debug logging to see detailed information:

```yaml
logger:
  default: info
  logs:
    custom_components.tesco_ie: debug
    custom_components.tesco_ie.tesco_api: debug
```

This will log:
- Session creation and closure
- Login indicators found
- Selector match counts
- Rate limiting timing
- API responses

## Inspecting Tesco.ie HTML Structure

To update selectors for real Tesco.ie pages:

### Using Browser Developer Tools

1. **Open Tesco.ie** in your browser
2. **Log in** to your account
3. **Open Developer Tools** (F12 or right-click → Inspect)
4. **Navigate** to the page you want to inspect (account, basket, etc.)

### Finding Clubcard Points

1. Go to your account page
2. In Developer Tools, press Ctrl+F (search)
3. Search for your Clubcard points number
4. Identify the HTML element containing the points
5. Note the class names or IDs used
6. Update the selector in `_parse_clubcard_points()` method

Example:
```python
clubcard_elements = soup.find_all(
    ["div", "span", "p"],
    class_=re.compile(r"actual-class-name", re.I)
)
```

### Finding Product Listings

1. Search for a product on Tesco.ie
2. Inspect a product tile/card in the search results
3. Note the container class (e.g., `product-tile`, `product-card`)
4. Update in `async_search_products()` method

### Finding Basket Items

1. Add items to your basket
2. Go to basket page
3. Inspect a basket item
4. Note the item container class
5. Update in `async_get_basket()` method

### Network Tab Analysis

Use the **Network** tab in Developer Tools to:
- See CSRF token locations in form submissions
- Identify API endpoints Tesco uses
- Understand request/response formats
- Find authentication cookies

## FAQ

### Is this safe to use with my Tesco account?

This integration uses your Tesco.ie credentials the same way a web browser would. Passwords are encrypted by Home Assistant's storage system. However, web scraping against Tesco's Terms of Service may risk account restrictions.

### Why web scraping instead of an official API?

Tesco Ireland does not provide a public API for customer accounts. Web scraping is the only method to access your account data programmatically.

### Will this work if Tesco updates their website?

No - the integration uses HTML selectors that target specific website elements. When Tesco updates their site structure, you'll need to update the selectors in `tesco_api.py`.

### Can I use multiple Tesco accounts?

Yes! The integration supports multiple config entries. Each account will have its own set of sensors and can be selected in services using the `entry_id` parameter.

### How does inventory tracking work?

The integration tracks items by delivery batch using FIFO (First In, First Out). When you ingest a receipt, items are added with a batch ID and timestamp. When you remove items (consumption), the oldest batches are used first.

### Can I track delivery batches?

Yes! The inventory sensor stores delivery metadata including:
- Batch ID (unique per delivery)
- Delivery timestamp
- Order number (if provided)
- Quantity per batch

Access this via the sensor's `items` attribute in Home Assistant.

### Does this support Tesco Ireland or Tesco UK?

This integration is specifically for **Tesco Ireland** (tesco.ie). Tesco UK (tesco.com) has a different website structure and would require separate selectors.

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
