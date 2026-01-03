"""Tests for Tesco Ireland integration initialization."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.tesco_ie import async_setup_entry, async_unload_entry
from custom_components.tesco_ie.const import DOMAIN


@pytest.mark.asyncio
async def test_setup_entry_success(hass: HomeAssistant, mock_tesco_api, mock_config_entry):
    """Test successful setup of config entry."""
    with patch(
        "custom_components.tesco_ie.TescoAPI",
        return_value=mock_tesco_api,
    ), patch(
        "custom_components.tesco_ie.async_forward_entry_setups",
        return_value=True,
    ) as mock_forward:
        result = await async_setup_entry(hass, mock_config_entry)

        assert result is True
        assert DOMAIN in hass.data
        assert mock_config_entry.entry_id in hass.data[DOMAIN]
        assert "coordinator" in hass.data[DOMAIN][mock_config_entry.entry_id]
        assert "api" in hass.data[DOMAIN][mock_config_entry.entry_id]
        mock_tesco_api.async_login.assert_called_once()


@pytest.mark.asyncio
async def test_setup_entry_auth_failure(hass: HomeAssistant, mock_config_entry):
    """Test setup fails with authentication error."""
    mock_api = AsyncMock()
    mock_api.async_login.side_effect = Exception("Auth failed")

    with patch(
        "custom_components.tesco_ie.TescoAPI",
        return_value=mock_api,
    ):
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, mock_config_entry)


@pytest.mark.asyncio
async def test_unload_entry(hass: HomeAssistant, mock_tesco_api, mock_config_entry):
    """Test unloading a config entry."""
    # Setup first
    with patch(
        "custom_components.tesco_ie.TescoAPI",
        return_value=mock_tesco_api,
    ), patch(
        "custom_components.tesco_ie.async_forward_entry_setups",
        return_value=True,
    ):
        await async_setup_entry(hass, mock_config_entry)

    assert mock_config_entry.entry_id in hass.data[DOMAIN]

    # Now unload
    with patch(
        "custom_components.tesco_ie.async_unload_platforms",
        return_value=True,
    ):
        result = await async_unload_entry(hass, mock_config_entry)

        assert result is True
        assert mock_config_entry.entry_id not in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_coordinator_update(hass: HomeAssistant, mock_tesco_api, mock_config_entry):
    """Test coordinator updates data."""
    with patch(
        "custom_components.tesco_ie.TescoAPI",
        return_value=mock_tesco_api,
    ), patch(
        "custom_components.tesco_ie.async_forward_entry_setups",
        return_value=True,
    ):
        await async_setup_entry(hass, mock_config_entry)

        coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]["coordinator"]

        # Trigger update
        await coordinator.async_refresh()

        assert coordinator.data is not None
        assert "clubcard_points" in coordinator.data
        mock_tesco_api.async_get_data.assert_called()
