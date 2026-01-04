"""Fixtures for Tesco Ireland integration tests."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from custom_components.tesco_ie.const import DOMAIN


@pytest.fixture
def mock_setup_entry() -> AsyncMock:
    """Mock setting up a config entry."""
    with patch(
        "custom_components.tesco_ie.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_tesco_api():
    """Mock TescoAPI."""
    with patch("custom_components.tesco_ie.tesco_api.TescoAPI") as mock_api:
        api_instance = mock_api.return_value
        api_instance.async_login = AsyncMock(return_value=True)
        api_instance.async_get_data = AsyncMock(
            return_value={
                "clubcard_points": 150,
                "next_delivery": None,
                "delivery_slot": None,
                "order_number": None,
                "basket_items": [],
            }
        )
        api_instance.async_search_products = AsyncMock(
            return_value=[
                {"id": "12345", "name": "Milk 2L", "price": "€1.50"},
                {"id": "67890", "name": "Milk 1L", "price": "€0.99"},
            ]
        )
        api_instance.async_add_to_basket = AsyncMock(
            return_value={"success": True, "message": "Item added", "response_data": {}}
        )
        api_instance.async_get_basket = AsyncMock(
            return_value=[
                {"name": "Milk 2L", "quantity": 2},
                {"name": "Bread", "quantity": 1},
            ]
        )
        api_instance.async_close = AsyncMock()
        yield api_instance


@pytest.fixture
def mock_config_entry():
    """Mock a config entry."""
    entry = MagicMock(
        domain=DOMAIN,
        data={
            CONF_EMAIL: "test@example.com",
            CONF_PASSWORD: "test_password",
        },
        options={},
        entry_id="test_entry_id",
        title="Tesco IE (test@example.com)",
    )
    entry.add_update_listener = MagicMock(return_value=lambda: None)
    entry.async_on_unload = MagicMock()
    return entry


@pytest.fixture
def mock_aiohttp_session():
    """Mock aiohttp ClientSession."""
    with patch("aiohttp.ClientSession") as mock_session:
        session_instance = mock_session.return_value
        session_instance.closed = False
        session_instance.close = AsyncMock()
        session_instance.get = AsyncMock()
        session_instance.post = AsyncMock()
        yield session_instance


@pytest.fixture
def mock_successful_login_response():
    """Mock successful login response."""
    response = AsyncMock()
    response.status = 200
    response.text = AsyncMock(
        return_value="""
        <html>
            <head>
                <meta name="csrf-token" content="test_csrf_token">
            </head>
            <body>
                <div class="account">
                    <p>Welcome, test@example.com</p>
                    <a href="/logout">Sign Out</a>
                    <div class="clubcard">
                        <p>Your Clubcard Points: 150 points</p>
                    </div>
                </div>
            </body>
        </html>
        """
    )
    return response


@pytest.fixture
def mock_failed_login_response():
    """Mock failed login response."""
    response = AsyncMock()
    response.status = 200
    response.text = AsyncMock(
        return_value="""
        <html>
            <body>
                <div class="error">Invalid email or password</div>
            </body>
        </html>
        """
    )
    return response


@pytest.fixture
def mock_account_page_response():
    """Mock account page response with Clubcard points and delivery info."""
    response = AsyncMock()
    response.status = 200
    response.text = AsyncMock(
        return_value="""
        <html>
            <body>
                <div class="clubcard-points">
                    <span>250 points</span>
                </div>
                <div class="delivery-info">
                    <p>Next delivery: 15 Jan 2024</p>
                    <p>Order #123456</p>
                </div>
            </body>
        </html>
        """
    )
    return response


@pytest.fixture
def mock_product_search_response():
    """Mock product search response."""
    response = AsyncMock()
    response.status = 200
    response.text = AsyncMock(
        return_value="""
        <html>
            <body>
                <div class="product-tile" data-product-id="12345">
                    <h3 class="product-name">Milk 2L</h3>
                    <span class="price-value">€1.50</span>
                </div>
                <div class="product-tile" data-product-id="67890">
                    <h3 class="product-name">Milk 1L</h3>
                    <span class="price-value">€0.99</span>
                </div>
            </body>
        </html>
        """
    )
    return response


@pytest.fixture
def mock_basket_response():
    """Mock basket page response."""
    response = AsyncMock()
    response.status = 200
    response.text = AsyncMock(
        return_value="""
        <html>
            <body>
                <div class="basket-item">
                    <span class="item-name">Milk 2L</span>
                    <span class="quantity">2</span>
                </div>
                <div class="basket-item">
                    <span class="item-name">Bread</span>
                    <span class="quantity">1</span>
                </div>
            </body>
        </html>
        """
    )
    return response
