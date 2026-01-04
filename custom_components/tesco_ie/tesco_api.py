"""Tesco Ireland API client with web scraping.

IMPORTANT: This implementation uses placeholder HTML selectors for demonstration purposes.
Before using in production, you MUST:
1. Inspect actual Tesco.ie HTML structure using browser developer tools
2. Update all CSS selectors to match real page elements
3. Test extensively with real credentials against the live site
4. Handle anti-bot measures (CAPTCHA, rate limiting, account lockouts)

The current selectors are generic patterns that may not work with the actual Tesco.ie website.
This serves as a template that requires site-specific customization.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, TypedDict

import aiohttp
from aiohttp import CookieJar
from bs4 import BeautifulSoup

from .const import MAX_SEARCH_RESULTS

_LOGGER = logging.getLogger(__name__)


# TypedDict definitions for structured returns
class ProductDict(TypedDict):
    """Product information structure."""

    id: str
    name: str
    price: str


class DeliveryInfoDict(TypedDict):
    """Delivery information structure."""

    next_delivery: str | None
    delivery_slot: str | None
    order_number: str | None


class BasketItemDict(TypedDict):
    """Basket item structure."""

    name: str
    quantity: int


class TescoDataDict(TypedDict):
    """Complete Tesco data structure."""

    clubcard_points: int
    next_delivery: str | None
    delivery_slot: str | None
    order_number: str | None
    basket_items: list[BasketItemDict]


class BasketOperationResult(TypedDict):
    """Result of basket operation."""

    success: bool
    message: str
    response_data: dict[str, Any] | None


# Tesco Ireland URLs
TESCO_BASE_URL = "https://www.tesco.ie"
TESCO_LOGIN_URL = f"{TESCO_BASE_URL}/login"
TESCO_GROCERIES_URL = f"{TESCO_BASE_URL}/groceries"
TESCO_ACCOUNT_URL = f"{TESCO_BASE_URL}/account"
TESCO_BASKET_URL = f"{TESCO_BASE_URL}/groceries/basket"
TESCO_SEARCH_URL = f"{TESCO_BASE_URL}/groceries/search"

# User agent to mimic a real browser
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Constants
RATE_LIMIT_DELAY_READ = 1.0  # seconds for read operations
RATE_LIMIT_DELAY_WRITE = 2.0  # seconds for write operations (more conservative)
DEFAULT_TIMEOUT = 30  # seconds

# Login success indicators
LOGIN_SUCCESS_INDICATORS = ["my account", "clubcard", "sign out", "logout"]

# Selector validation error messages
SELECTOR_ERROR_MESSAGES = {
    "clubcard_points": "Unable to find Clubcard points on page. Website structure may have changed.",
    "delivery_info": "Unable to find delivery information. Website structure may have changed.",
    "product_search": "Unable to find product listings. Website structure may have changed.",
    "basket_items": "Unable to parse basket items. Website structure may have changed.",
}


class TescoAuthError(Exception):
    """Exception for authentication errors."""


class TescoAPIError(Exception):
    """Exception for API errors."""


class SelectorValidationError(TescoAPIError):
    """Exception for selector validation failures."""

    def __init__(self, selector_type: str, details: str = "") -> None:
        """Initialize with selector type and optional details."""
        base_message = SELECTOR_ERROR_MESSAGES.get(
            selector_type, "Selector validation failed"
        )
        full_message = f"{base_message} {details}".strip()
        super().__init__(full_message)
        self.selector_type = selector_type


class TescoAPI:
    """Tesco Ireland API client using web scraping."""

    def __init__(
        self,
        email: str,
        password: str,
        timeout: int = DEFAULT_TIMEOUT,
        rate_limit_read: float = RATE_LIMIT_DELAY_READ,
        rate_limit_write: float = RATE_LIMIT_DELAY_WRITE,
    ) -> None:
        """Initialize the API client.

        Args:
            email: Tesco account email
            password: Tesco account password
            timeout: Request timeout in seconds (default: 30)
            rate_limit_read: Rate limit for read operations in seconds (default: 1.0)
            rate_limit_write: Rate limit for write operations in seconds (default: 2.0)
        """
        self.email = email
        self.password = password
        self.timeout = timeout
        self.rate_limit_read = rate_limit_read
        self.rate_limit_write = rate_limit_write
        self._session: aiohttp.ClientSession | None = None
        self._cookie_jar: CookieJar | None = None
        self._logged_in = False
        self._csrf_token: str | None = None
        self._last_request_time_read: float | None = None
        self._last_request_time_write: float | None = None
        self._failed_login_attempts = 0
        self._last_login_attempt_time: float | None = None

    async def _create_session(self) -> None:
        """Create an aiohttp session with proper headers and cookie jar."""
        if self._session is None or self._session.closed:
            _LOGGER.debug("Creating new aiohttp session with timeout=%ds", self.timeout)
            # Use secure cookie jar (removed unsafe=True)
            self._cookie_jar = CookieJar()
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            self._session = aiohttp.ClientSession(
                cookie_jar=self._cookie_jar,
                timeout=timeout,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-IE,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            _LOGGER.debug("Session created successfully")
        else:
            _LOGGER.debug("Reusing existing session")

    async def _ensure_session(self) -> None:
        """Ensure session is initialized and valid."""
        if self._session is None or self._session.closed:
            await self._create_session()

    @property
    def is_logged_in(self) -> bool:
        """Return whether the API is currently logged in (for diagnostic purposes)."""
        return self._logged_in

    @property
    def has_csrf_token(self) -> bool:
        """Return whether a CSRF token is available (for diagnostic purposes)."""
        return self._csrf_token is not None

    async def _rate_limit(self, is_write: bool = False) -> None:
        """Implement rate limiting to avoid being blocked.

        Uses monotonic clock for accurate timing.
        Separate rate limits for read vs write operations.

        Args:
            is_write: If True, use write operation rate limit (more conservative)
        """
        delay = self.rate_limit_write if is_write else self.rate_limit_read
        last_request_time = (
            self._last_request_time_write if is_write else self._last_request_time_read
        )

        if last_request_time:
            elapsed = time.monotonic() - last_request_time
            if elapsed < delay:
                await asyncio.sleep(delay - elapsed)

        current_time = time.monotonic()
        if is_write:
            self._last_request_time_write = current_time
        else:
            self._last_request_time_read = current_time

    async def _get_csrf_token(self, html: str) -> str | None:
        """Extract CSRF token from HTML.

        Checks multiple common locations for CSRF tokens.
        """
        soup = BeautifulSoup(html, "lxml")

        # Look for CSRF token in meta tags
        csrf_meta = soup.find("meta", {"name": "csrf-token"})
        if csrf_meta and csrf_meta.get("content"):
            token = csrf_meta["content"]
            _LOGGER.debug("Found CSRF token in meta tag")
            return token

        # Look for CSRF token in hidden inputs
        csrf_input = soup.find("input", {"name": "_csrf"})
        if csrf_input and csrf_input.get("value"):
            _LOGGER.debug("Found CSRF token in input field")
            return csrf_input["value"]

        # Look for CSRF token in script tags
        for script in soup.find_all("script"):
            if script.string:
                # Try both assignment (=) and property (:) patterns
                csrf_match = re.search(
                    r'csrfToken["\']?\s*[=:]\s*["\']([^"\']+)', script.string
                )
                if csrf_match:
                    _LOGGER.debug("Found CSRF token in script")
                    return csrf_match.group(1)

        _LOGGER.debug("No CSRF token found")
        return None

    def _validate_selector_results(
        self, found_elements: int, selector_type: str, warn_only: bool = True
    ) -> bool:
        """Validate that selectors found expected elements.

        Args:
            found_elements: Number of elements found by selector
            selector_type: Type of selector for error message lookup
            warn_only: If True, only log warning; if False, raise exception

        Returns:
            True if validation passed, False otherwise

        Raises:
            SelectorValidationError: If warn_only=False and validation fails
        """
        if found_elements == 0:
            error_msg = SELECTOR_ERROR_MESSAGES.get(
                selector_type, f"No elements found for {selector_type}"
            )
            if warn_only:
                _LOGGER.warning("%s Found %d elements.", error_msg, found_elements)
                return False
            else:
                raise SelectorValidationError(
                    selector_type, f"Found {found_elements} elements"
                )

        _LOGGER.debug(
            "Selector validation passed for %s: found %d elements",
            selector_type,
            found_elements,
        )
        return True

    async def async_login(self) -> bool:
        """Login to Tesco Ireland using web scraping with exponential backoff.

        Note: This implementation does NOT handle anti-bot measures such as:
        - CAPTCHA challenges
        - IP-based rate limiting beyond basic exponential backoff
        - Account lockouts from suspicious activity

        If you encounter authentication failures, you may need to:
        - Manually log in through a browser to solve CAPTCHA
        - Wait for IP rate limits to reset
        - Contact Tesco support if your account is locked
        """
        _LOGGER.info("Authenticating with Tesco Ireland")

        # Implement exponential backoff for failed login attempts
        if self._failed_login_attempts > 0 and self._last_login_attempt_time:
            backoff_delay = min(2**self._failed_login_attempts, 300)  # Max 5 minutes
            elapsed = time.monotonic() - self._last_login_attempt_time
            if elapsed < backoff_delay:
                remaining = backoff_delay - elapsed
                _LOGGER.warning(
                    "Rate limiting login attempts due to %d previous failures. "
                    "Waiting %.1f more seconds before retry.",
                    self._failed_login_attempts,
                    remaining,
                )
                await asyncio.sleep(remaining)

        self._last_login_attempt_time = time.monotonic()

        try:
            await self._create_session()

            try:
                await self._rate_limit()

                # Step 1: Get the login page to obtain CSRF token and cookies
                async with self._session.get(TESCO_LOGIN_URL) as response:
                    if response.status != 200:
                        raise TescoAuthError(
                            f"Failed to load login page: {response.status}"
                        )

                    html = await response.text()
                    self._csrf_token = await self._get_csrf_token(html)

                await self._rate_limit()

                # Step 2: Submit login credentials
                login_data = {
                    "username": self.email,
                    "password": self.password,
                }

                if self._csrf_token:
                    login_data["_csrf"] = self._csrf_token

                headers = {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": TESCO_LOGIN_URL,
                    "Origin": TESCO_BASE_URL,
                }

                async with self._session.post(
                    TESCO_LOGIN_URL,
                    data=login_data,
                    headers=headers,
                    allow_redirects=True,
                ) as response:
                    # Check if login was successful
                    if response.status in (200, 302, 303):
                        # Verify we're logged in by checking for account-specific content
                        html = await response.text()

                        # Look for indicators of successful login
                        found_indicators = [
                            indicator
                            for indicator in LOGIN_SUCCESS_INDICATORS
                            if indicator in html.lower()
                        ]

                        if found_indicators:
                            self._logged_in = True
                            self._failed_login_attempts = 0  # Reset on success
                            # Clear password from memory after successful login for security
                            self.password = None
                            _LOGGER.info("Successfully authenticated")
                            _LOGGER.debug(
                                "Login verified by indicators: %s",
                                ", ".join(found_indicators),
                            )
                            return True
                        else:
                            # Check for error messages
                            soup = BeautifulSoup(html, "lxml")
                            error_elements = soup.find_all(
                                class_=re.compile(r"error|alert|warning", re.I)
                            )
                            error_msg = " ".join(
                                elem.get_text(strip=True) for elem in error_elements[:3]
                            )
                            self._failed_login_attempts += 1
                            _LOGGER.warning(
                                "Login attempt %d failed: invalid credentials",
                                self._failed_login_attempts,
                            )
                            raise TescoAuthError(
                                f"Login failed: {error_msg or 'Invalid credentials'}"
                            )
                    else:
                        self._failed_login_attempts += 1
                        _LOGGER.warning(
                            "Login attempt %d failed: HTTP %s",
                            self._failed_login_attempts,
                            response.status,
                        )
                        raise TescoAuthError(
                            f"Login failed with status: {response.status}"
                        )
            except (aiohttp.ClientError, TescoAuthError):
                # Clean up session on error
                if self._session and not self._session.closed:
                    await self._session.close()
                    self._session = None
                raise

        except aiohttp.ClientError as err:
            self._failed_login_attempts += 1
            _LOGGER.error(
                "Network error during login (attempt %d)", self._failed_login_attempts
            )
            raise TescoAuthError(f"Network error: {err}") from err
        except TescoAuthError:
            # Re-raise TescoAuthError without incrementing counter again
            raise
        except (AttributeError, KeyError, TypeError, ValueError) as err:
            # Handle HTML parsing errors
            self._failed_login_attempts += 1
            _LOGGER.error(
                "HTML parsing error during login (attempt %d): %s",
                self._failed_login_attempts,
                err,
            )
            raise TescoAuthError(f"Failed to parse login response: {err}") from err

    async def async_get_data(self) -> TescoDataDict:
        """Fetch data from Tesco including Clubcard points and delivery info."""
        if not self._logged_in:
            await self.async_login()

        await self._ensure_session()

        try:
            await self._rate_limit()

            # Fetch account page to get Clubcard points and delivery information
            async with self._session.get(TESCO_ACCOUNT_URL) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, "lxml")

                    # Parse Clubcard points
                    clubcard_points = await self._parse_clubcard_points(soup)

                    # Parse delivery information
                    delivery_info = await self._parse_delivery_info(soup)

                    return {
                        "clubcard_points": clubcard_points,
                        "next_delivery": delivery_info.get("next_delivery"),
                        "delivery_slot": delivery_info.get("delivery_slot"),
                        "order_number": delivery_info.get("order_number"),
                        "basket_items": await self.async_get_basket(),
                    }
                else:
                    _LOGGER.warning("Failed to fetch account data: %s", response.status)
                    return {
                        "clubcard_points": 0,
                        "next_delivery": None,
                        "basket_items": [],
                    }

        except Exception as err:
            _LOGGER.error("Error fetching Tesco data")
            raise TescoAPIError(f"Failed to fetch data: {err}") from err

    async def _parse_clubcard_points(self, soup: BeautifulSoup) -> int:
        """Parse Clubcard points from account page."""
        # Look for Clubcard points in various possible locations
        # Use specific selectors for better reliability
        points_patterns = [
            r"(\d+)\s*points?",
            r"clubcard.*?(\d+)",
            r"points.*?(\d+)",
        ]

        # Search in specific clubcard elements first
        clubcard_elements = soup.find_all(
            ["div", "span", "p"], class_=re.compile(r"clubcard.*points?", re.I)
        )

        # Validate selector found elements
        self._validate_selector_results(
            len(clubcard_elements), "clubcard_points", warn_only=True
        )

        for elem in clubcard_elements:
            text = elem.get_text()
            for pattern in points_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    try:
                        return int(match.group(1))
                    except (ValueError, IndexError):
                        continue

        # Fallback to broader search
        text = soup.get_text()
        for pattern in points_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    return int(match.group(1))
                except (ValueError, IndexError):
                    continue

        _LOGGER.debug("Could not find Clubcard points")
        return 0

    async def _parse_delivery_info(self, soup: BeautifulSoup) -> DeliveryInfoDict:
        """Parse delivery information from account page."""
        delivery_info = {
            "next_delivery": None,
            "delivery_slot": None,
            "order_number": None,
        }

        # Look for delivery-specific elements with more targeted selectors
        delivery_elements = soup.find_all(
            ["div", "section"], class_=re.compile(r"delivery|order", re.I)
        )

        for elem in delivery_elements:
            text = elem.get_text(strip=True)

            # Try to extract date
            date_match = re.search(
                r"(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+(\d{4})",
                text,
                re.IGNORECASE,
            )
            if date_match and not delivery_info["next_delivery"]:
                delivery_info["next_delivery"] = date_match.group(0)

            # Try to extract delivery slot (time range like "10:00 - 12:00")
            slot_match = re.search(
                r"(\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2})",
                text,
                re.IGNORECASE,
            )
            if slot_match and not delivery_info["delivery_slot"]:
                delivery_info["delivery_slot"] = slot_match.group(0)

            # Try to extract order number
            order_match = re.search(r"order\s*#?\s*(\d+)", text, re.IGNORECASE)
            if order_match:
                delivery_info["order_number"] = order_match.group(1)

        return delivery_info

    async def async_search_products(self, query: str) -> list[ProductDict]:
        """Search for products on Tesco."""
        if not self._logged_in:
            await self.async_login()

        await self._ensure_session()

        try:
            await self._rate_limit()

            search_url = f"{TESCO_SEARCH_URL}?query={query}"

            async with self._session.get(search_url) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, "lxml")

                    products = []

                    # Use more specific product selectors
                    # These may need adjustment based on actual Tesco.ie HTML structure
                    product_containers = soup.find_all(
                        ["article", "div"],
                        class_=re.compile(
                            r"product-tile|product-card|product-list-item", re.I
                        ),
                    )

                    # Validate selector results
                    self._validate_selector_results(
                        len(product_containers), "product_search", warn_only=True
                    )

                    for elem in product_containers[:MAX_SEARCH_RESULTS]:
                        try:
                            # Extract product information with specific selectors
                            product_id = (
                                elem.get("data-product-id")
                                or elem.get("data-product")
                                or elem.get("id")
                            )

                            name_elem = elem.find(
                                ["h2", "h3", "a"],
                                class_=re.compile(r"product-title|product-name", re.I),
                            )

                            price_elem = elem.find(
                                ["span", "div"],
                                class_=re.compile(r"price-value|product-price", re.I),
                            )

                            if name_elem:
                                product = {
                                    "id": product_id or f"product_{len(products)}",
                                    "name": name_elem.get_text(strip=True),
                                    "price": (
                                        price_elem.get_text(strip=True)
                                        if price_elem
                                        else "N/A"
                                    ),
                                }
                                products.append(product)
                        except Exception:
                            # Log at debug level to avoid spam
                            _LOGGER.debug("Error parsing product element")
                            continue

                    _LOGGER.info("Found %d products", len(products))
                    return products
                else:
                    _LOGGER.warning("Product search failed: %s", response.status)
                    return []

        except Exception:
            _LOGGER.error("Error searching products")
            return []

    async def async_add_to_basket(
        self, product_id: str, quantity: int = 1
    ) -> BasketOperationResult:
        """Add item to shopping basket with validation.

        Args:
            product_id: Product identifier
            quantity: Quantity to add

        Returns:
            BasketOperationResult with success status, message, and response data
        """
        if not self._logged_in:
            await self.async_login()

        await self._ensure_session()

        try:
            await self._rate_limit(is_write=True)  # Use write rate limit

            # Prepare basket addition request
            basket_add_url = f"{TESCO_GROCERIES_URL}/api/basket/add"

            data = {
                "productId": product_id,
                "quantity": quantity,
            }

            if self._csrf_token:
                data["_csrf"] = self._csrf_token

            headers = {
                "Content-Type": "application/json",
                "Referer": TESCO_GROCERIES_URL,
                "X-Requested-With": "XMLHttpRequest",
            }

            async with self._session.post(
                basket_add_url,
                json=data,
                headers=headers,
            ) as response:
                response_text = await response.text()

                # Validate response
                if response.status in (200, 201):
                    try:
                        response_data = await response.json() if response_text else {}
                    except Exception:
                        response_data = {"raw_response": response_text}

                    _LOGGER.info("Successfully added item to basket")
                    return {
                        "success": True,
                        "message": "Item added to basket successfully",
                        "response_data": response_data,
                    }
                else:
                    _LOGGER.warning(
                        "Failed to add to basket: HTTP %s - %s",
                        response.status,
                        response_text[:200],
                    )
                    return {
                        "success": False,
                        "message": f"Failed with HTTP {response.status}",
                        "response_data": {
                            "status": response.status,
                            "error": response_text[:200],
                        },
                    }

        except TescoAuthError as err:
            _LOGGER.error("Authentication error adding to basket: %s", err)
            return {
                "success": False,
                "message": f"Authentication error: {err}",
                "response_data": None,
            }
        except Exception as err:
            _LOGGER.error("Error adding to basket: %s", err)
            return {
                "success": False,
                "message": f"Error: {err}",
                "response_data": None,
            }

    async def async_get_basket(self) -> list[BasketItemDict]:
        """Get current basket items."""
        if not self._logged_in:
            await self.async_login()

        await self._ensure_session()

        try:
            await self._rate_limit()

            async with self._session.get(TESCO_BASKET_URL) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, "lxml")

                    items = []

                    # Use specific basket item selectors
                    item_elements = soup.find_all(
                        ["div", "li"], class_=re.compile(r"basket-item|cart-item", re.I)
                    )

                    # Validate selector results
                    self._validate_selector_results(
                        len(item_elements), "basket_items", warn_only=True
                    )

                    for elem in item_elements:
                        try:
                            name_elem = elem.find(
                                ["span", "h3", "a"],
                                class_=re.compile(r"item-name|product-name", re.I),
                            )
                            qty_elem = elem.find(
                                ["input", "span"],
                                class_=re.compile(r"quantity|qty", re.I),
                            )

                            if name_elem:
                                item = {
                                    "name": name_elem.get_text(strip=True),
                                    "quantity": (
                                        int(qty_elem.get_text(strip=True))
                                        if qty_elem
                                        else 1
                                    ),
                                }
                                items.append(item)
                        except Exception:
                            _LOGGER.debug("Error parsing basket item")
                            continue

                    return items
                else:
                    _LOGGER.warning("Failed to fetch basket: %s", response.status)
                    return []

        except Exception:
            _LOGGER.error("Error fetching basket")
            return []

    async def async_close(self) -> None:
        """Close the API session and cleanup resources."""
        if self._session and not self._session.closed:
            _LOGGER.debug("Closing aiohttp session")
            await self._session.close()
            self._session = None

        was_logged_in = self._logged_in
        self._logged_in = False
        self._csrf_token = None
        self._cookie_jar = None

        if was_logged_in:
            _LOGGER.debug("API session closed (was logged in)")
        else:
            _LOGGER.debug("API session closed (was not logged in)")
