"""Tests for Tesco Ireland config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from custom_components.tesco_ie.config_flow import TescoIEConfigFlow
from custom_components.tesco_ie.const import DOMAIN
from custom_components.tesco_ie.tesco_api import TescoAuthError


@pytest.mark.asyncio
async def test_form_shown(hass: HomeAssistant):
    """Test that the form is shown when no user input."""
    flow = TescoIEConfigFlow()
    flow.hass = hass

    result = await flow.async_step_user(user_input=None)

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {}


@pytest.mark.asyncio
async def test_successful_config_entry(hass: HomeAssistant, mock_tesco_api):
    """Test successful creation of config entry."""
    flow = TescoIEConfigFlow()
    flow.hass = hass

    # Mock the unique_id methods to avoid mappingproxy issues
    with patch.object(flow, 'async_set_unique_id'), \
         patch.object(flow, '_abort_if_unique_id_configured'), \
         patch("custom_components.tesco_ie.config_flow.TescoAPI", return_value=mock_tesco_api):
        result = await flow.async_step_user(
            user_input={
                CONF_EMAIL: "test@example.com",
                CONF_PASSWORD: "password123",
            }
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Tesco IE (test@example.com)"
    assert result["data"] == {
        CONF_EMAIL: "test@example.com",
        CONF_PASSWORD: "password123",
    }
    mock_tesco_api.async_login.assert_called_once()


@pytest.mark.asyncio
async def test_invalid_auth(hass: HomeAssistant):
    """Test invalid authentication."""
    flow = TescoIEConfigFlow()
    flow.hass = hass

    mock_api = AsyncMock()
    mock_api.async_login.side_effect = TescoAuthError("Invalid credentials")

    with patch(
        "custom_components.tesco_ie.config_flow.TescoAPI",
        return_value=mock_api,
    ):
        result = await flow.async_step_user(
            user_input={
                CONF_EMAIL: "test@example.com",
                CONF_PASSWORD: "wrong_password",
            }
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_unknown_error(hass: HomeAssistant):
    """Test handling of unknown errors."""
    flow = TescoIEConfigFlow()
    flow.hass = hass

    mock_api = AsyncMock()
    mock_api.async_login.side_effect = Exception("Unknown error")

    with patch(
        "custom_components.tesco_ie.config_flow.TescoAPI",
        return_value=mock_api,
    ):
        result = await flow.async_step_user(
            user_input={
                CONF_EMAIL: "test@example.com",
                CONF_PASSWORD: "password123",
            }
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


@pytest.mark.asyncio
async def test_duplicate_entry(hass: HomeAssistant, mock_tesco_api):
    """Test that duplicate entries are prevented."""
    entry_data = {
        CONF_EMAIL: "test@example.com",
        CONF_PASSWORD: "password123",
    }

    with patch("custom_components.tesco_ie.config_flow.TescoAPI", return_value=mock_tesco_api):
        # Create first entry
        flow1 = TescoIEConfigFlow()
        flow1.hass = hass

        with patch.object(flow1, 'async_set_unique_id'), \
             patch.object(flow1, '_abort_if_unique_id_configured'):
            result1 = await flow1.async_step_user(user_input=entry_data)

        # Verify first entry was created
        assert result1["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

        # Try to add duplicate - mock _abort_if_unique_id_configured to raise
        flow2 = TescoIEConfigFlow()
        flow2.hass = hass

        def abort_duplicate():
            raise data_entry_flow.AbortFlow("already_configured")

        with patch.object(flow2, 'async_set_unique_id'), \
             patch.object(flow2, '_abort_if_unique_id_configured', side_effect=abort_duplicate):
            result2 = await flow2.async_step_user(user_input=entry_data)

        assert result2["type"] == data_entry_flow.FlowResultType.ABORT
        assert result2["reason"] == "already_configured"
