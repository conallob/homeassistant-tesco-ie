"""Tests for Tesco Ireland API client."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from bs4 import BeautifulSoup

from custom_components.tesco_ie.tesco_api import (
    TescoAPI,
    TescoAPIError,
    TescoAuthError,
)


class AsyncContextManagerMock:
    """Helper to create async context manager mocks."""

    def __init__(self, return_value):
        """Initialize with the value to return from __aenter__."""
        self.return_value = return_value

    async def __aenter__(self):
        """Enter the context."""
        return self.return_value

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit the context."""
        return None


@pytest.mark.asyncio
async def test_api_initialization():
    """Test API client initialization."""
    api = TescoAPI("test@example.com", "password123")

    assert api.email == "test@example.com"
    assert api.password == "password123"
    assert api._session is None
    assert not api._logged_in
    assert api._csrf_token is None


@pytest.mark.asyncio
async def test_create_session():
    """Test session creation with proper headers."""
    api = TescoAPI("test@example.com", "password123")

    await api._create_session()

    assert api._session is not None
    assert api._cookie_jar is not None
    assert not api._session.closed

    await api.async_close()


@pytest.mark.asyncio
async def test_csrf_token_extraction_from_meta():
    """Test CSRF token extraction from meta tag."""
    api = TescoAPI("test@example.com", "password123")

    html = '<html><head><meta name="csrf-token" content="test_token_123"></head></html>'
    token = await api._get_csrf_token(html)

    assert token == "test_token_123"


@pytest.mark.asyncio
async def test_csrf_token_extraction_from_input():
    """Test CSRF token extraction from hidden input."""
    api = TescoAPI("test@example.com", "password123")

    html = '<html><body><input type="hidden" name="_csrf" value="input_token_456"></body></html>'
    token = await api._get_csrf_token(html)

    assert token == "input_token_456"


@pytest.mark.asyncio
async def test_csrf_token_extraction_from_script():
    """Test CSRF token extraction from script tag."""
    api = TescoAPI("test@example.com", "password123")

    html = '<html><body><script>var csrfToken = "script_token_789";</script></body></html>'
    token = await api._get_csrf_token(html)

    assert token == "script_token_789"


@pytest.mark.asyncio
async def test_successful_login(mock_successful_login_response):
    """Test successful login flow."""
    api = TescoAPI("test@example.com", "password123")

    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        # Mock GET request for login page
        mock_session.get = MagicMock(
            return_value=AsyncContextManagerMock(mock_successful_login_response)
        )

        # Mock POST request for login submission
        mock_session.post = MagicMock(
            return_value=AsyncContextManagerMock(mock_successful_login_response)
        )

        result = await api.async_login()

        assert result is True
        assert api._logged_in is True
        assert api._csrf_token == "test_csrf_token"


@pytest.mark.asyncio
async def test_failed_login(
    mock_successful_login_response, mock_failed_login_response
):
    """Test failed login with invalid credentials."""
    api = TescoAPI("test@example.com", "wrong_password")

    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        # Mock GET request (successful to get login page)
        mock_session.get = MagicMock(
            return_value=AsyncContextManagerMock(mock_successful_login_response)
        )

        # Mock POST request with failed response
        mock_session.post = MagicMock(
            return_value=AsyncContextManagerMock(mock_failed_login_response)
        )

        with pytest.raises(TescoAuthError):
            await api.async_login()

        assert api._logged_in is False


@pytest.mark.asyncio
async def test_parse_clubcard_points():
    """Test parsing Clubcard points from HTML."""
    api = TescoAPI("test@example.com", "password123")

    html = """
    <html>
        <body>
            <div class="clubcard">
                <p>Your Clubcard Points: 250 points</p>
            </div>
        </body>
    </html>
    """
    soup = BeautifulSoup(html, "lxml")
    points = await api._parse_clubcard_points(soup)

    assert points == 250


@pytest.mark.asyncio
async def test_parse_clubcard_points_no_points():
    """Test parsing when no Clubcard points found."""
    api = TescoAPI("test@example.com", "password123")

    html = "<html><body><div>No points here</div></body></html>"
    soup = BeautifulSoup(html, "lxml")
    points = await api._parse_clubcard_points(soup)

    assert points == 0


@pytest.mark.asyncio
async def test_parse_delivery_info():
    """Test parsing delivery information from HTML."""
    api = TescoAPI("test@example.com", "password123")

    html = """
    <html>
        <body>
            <div class="delivery">
                <p>Next delivery: 15 January 2024</p>
                <p>Delivery slot: 10:00 - 12:00</p>
                <p>Order #123456</p>
            </div>
        </body>
    </html>
    """
    soup = BeautifulSoup(html, "lxml")
    info = await api._parse_delivery_info(soup)

    assert info["order_number"] == "123456"
    assert info["delivery_slot"] is not None
    assert info["next_delivery"] is not None


@pytest.mark.asyncio
async def test_get_data(mock_account_page_response, mock_basket_response):
    """Test fetching account data."""
    api = TescoAPI("test@example.com", "password123")
    api._logged_in = True

    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session_class.return_value = mock_session
        api._session = mock_session

        # Mock account page and basket page requests
        mock_session.get.side_effect = [
            AsyncContextManagerMock(mock_account_page_response),
            AsyncContextManagerMock(mock_basket_response),
        ]

        data = await api.async_get_data()

        assert "clubcard_points" in data
        assert "next_delivery" in data
        assert "basket_items" in data


@pytest.mark.asyncio
async def test_search_products(mock_product_search_response):
    """Test product search."""
    api = TescoAPI("test@example.com", "password123")
    api._logged_in = True

    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session_class.return_value = mock_session
        api._session = mock_session

        mock_session.get = MagicMock(
            return_value=AsyncContextManagerMock(mock_product_search_response)
        )

        products = await api.async_search_products("milk")

        assert len(products) > 0
        assert products[0]["id"] == "12345"
        assert "Milk" in products[0]["name"]


@pytest.mark.asyncio
async def test_add_to_basket():
    """Test adding item to basket."""
    api = TescoAPI("test@example.com", "password123")
    api._logged_in = True
    api._csrf_token = "test_token"

    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session_class.return_value = mock_session
        api._session = mock_session

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value='{"success": true}')
        mock_response.json = AsyncMock(return_value={"success": True})

        mock_session.post = MagicMock(
            return_value=AsyncContextManagerMock(mock_response)
        )

        result = await api.async_add_to_basket("12345", 2)

        assert result["success"] is True
        mock_session.post.assert_called_once()


@pytest.mark.asyncio
async def test_get_basket(mock_basket_response):
    """Test getting basket items."""
    api = TescoAPI("test@example.com", "password123")
    api._logged_in = True

    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session_class.return_value = mock_session
        api._session = mock_session

        mock_session.get = MagicMock(
            return_value=AsyncContextManagerMock(mock_basket_response)
        )

        items = await api.async_get_basket()

        assert len(items) > 0
        assert items[0]["name"] == "Milk 2L"
        assert items[0]["quantity"] == 2


@pytest.mark.asyncio
async def test_rate_limiting():
    """Test rate limiting between requests."""
    api = TescoAPI("test@example.com", "password123")

    # First request should not sleep
    await api._rate_limit()
    assert api._last_request_time_read is not None

    # Second immediate request should sleep
    import time

    start = time.time()
    await api._rate_limit()
    elapsed = time.time() - start

    # Should have slept approximately 1 second (rate_limit_delay)
    assert elapsed >= 0.9  # Allow some tolerance


@pytest.mark.asyncio
async def test_close_session():
    """Test closing the API session."""
    api = TescoAPI("test@example.com", "password123")

    await api._create_session()
    assert api._session is not None

    await api.async_close()

    assert api._session is None
    assert api._logged_in is False
    assert api._csrf_token is None


@pytest.mark.asyncio
async def test_network_error_handling():
    """Test handling of network errors."""
    api = TescoAPI("test@example.com", "password123")

    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session_class.return_value = mock_session

        # Simulate network error
        mock_session.get.side_effect = aiohttp.ClientError("Network error")

        with pytest.raises(TescoAuthError):
            await api.async_login()
