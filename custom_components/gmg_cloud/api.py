"""GMG Cloud API Client."""
from __future__ import annotations

import logging
import asyncio
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import (
    COGNITO_USER_POOL_ID,
    COGNITO_CLIENT_ID,
    COGNITO_REGION,
    API_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)


class GMGAuthError(Exception):
    """Authentication error."""


class GMGApiError(Exception):
    """API error."""


class GMGCloudApi:
    """GMG Cloud API client.

    Discovered from reverse engineering the GMG Prime Flutter app:
    - Auth: AWS Cognito SRP (us-east-1)
    - State endpoint: GET /grill/{connectionType}|{grillId}/state
    - Command endpoint: POST /grill/{connectionType}|{grillId}/command
      (Content-Type: application/octet-stream)
    """

    def __init__(self, email: str, password: str) -> None:
        """Initialize the API client."""
        self.email = email
        self.password = password
        self._id_token: str | None = None
        self._cognito: Any = None  # Cognito instance for token refresh
        self._session: aiohttp.ClientSession | None = None
        self._grills: list[dict] = []

    async def async_authenticate(self) -> bool:
        """Authenticate with AWS Cognito."""
        try:
            loop = asyncio.get_event_loop()
            self._id_token = await loop.run_in_executor(
                None, self._sync_authenticate
            )
            return self._id_token is not None
        except Exception as err:
            _LOGGER.error("Authentication failed: %s", err)
            raise GMGAuthError(f"Authentication failed: {err}") from err

    def _sync_authenticate(self) -> str | None:
        """Synchronous authentication with Cognito."""
        try:
            from pycognito import Cognito
        except ImportError:
            _LOGGER.error("pycognito not installed")
            raise GMGAuthError("pycognito package not installed")

        u = Cognito(
            COGNITO_USER_POOL_ID,
            COGNITO_CLIENT_ID,
            username=self.email,
        )
        u.authenticate(password=self.password)
        self._cognito = u
        _LOGGER.info("Authenticated with GMG Cloud as %s", self.email)
        return u.id_token

    async def _async_refresh_token(self) -> bool:
        """Refresh the authentication token if expired."""
        if not self._cognito:
            return await self.async_authenticate()
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._sync_refresh_token)
            return True
        except Exception as err:
            _LOGGER.warning("Token refresh failed, re-authenticating: %s", err)
            return await self.async_authenticate()

    def _sync_refresh_token(self) -> None:
        """Synchronous token refresh."""
        self._cognito.renew_access_token()
        self._id_token = self._cognito.id_token

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def _headers(self) -> dict[str, str]:
        """Get API headers. No Bearer prefix per GMG API."""
        return {
            "Authorization": self._id_token,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _grill_path(grill: dict) -> str:
        """Build the grill path segment: {connectionType}|{grillId}.

        Discovered from app decompilation: the API uses the 'sk' field format
        e.g. 'Grill|remote|41029462' -> path segment 'remote|41029462'.
        """
        conn_type = grill.get("connectionType", "remote")
        grill_id = grill.get("grillId", "")
        return quote(f"{conn_type}|{grill_id}", safe="")

    async def async_get_grills(self) -> list[dict]:
        """Get list of grills for the account."""
        if not self._id_token:
            raise GMGApiError("Not authenticated")

        session = await self._ensure_session()
        url = f"{API_BASE_URL}/grill"

        try:
            async with session.get(url, headers=self._headers()) as response:
                if response.status == 200:
                    self._grills = await response.json()
                    return self._grills
                elif response.status in (401, 403):
                    _LOGGER.info("Token expired, refreshing...")
                    if await self._async_refresh_token():
                        return await self.async_get_grills()
                    return []
                else:
                    text = await response.text()
                    _LOGGER.error("Failed to get grills: %s - %s", response.status, text)
                    return []
        except Exception as err:
            _LOGGER.error("Error getting grills: %s", err)
            return []

    async def async_get_grill_state(self, grill: dict) -> dict | None:
        """Get current state of a grill.

        Uses the correct endpoint: /grill/{connectionType}|{grillId}/state
        """
        if not self._id_token:
            raise GMGApiError("Not authenticated")

        session = await self._ensure_session()
        path = self._grill_path(grill)
        url = f"{API_BASE_URL}/grill/{path}/state"

        try:
            async with session.get(url, headers=self._headers()) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status in (401, 403):
                    _LOGGER.info("Token expired, refreshing...")
                    if await self._async_refresh_token():
                        return await self.async_get_grill_state(grill)
                    return None
                elif response.status == 404:
                    _LOGGER.debug("Grill %s not currently online", grill.get("grillId"))
                    return None
                else:
                    text = await response.text()
                    _LOGGER.warning("Failed to get grill state: %s - %s", response.status, text[:200])
                    return None
        except Exception as err:
            _LOGGER.error("Error getting grill state: %s", err)
            return None

    async def async_send_command(
        self, grill: dict, command_data: bytes
    ) -> bool:
        """Send command to grill.

        Uses the correct endpoint: /grill/{connectionType}|{grillId}/command
        with Content-Type: application/octet-stream (binary payload).
        """
        if not self._id_token:
            raise GMGApiError("Not authenticated")

        session = await self._ensure_session()
        path = self._grill_path(grill)
        url = f"{API_BASE_URL}/grill/{path}/command"

        headers = {
            "Authorization": self._id_token,
            "Content-Type": "application/octet-stream",
        }

        try:
            async with session.put(url, headers=headers, data=command_data) as response:
                if response.status in (200, 201, 202):
                    _LOGGER.info("Command sent successfully to %s", grill.get("grillId"))
                    return True
                elif response.status in (401, 403):
                    _LOGGER.info("Token expired, refreshing...")
                    if await self._async_refresh_token():
                        return await self.async_send_command(grill, command_data)
                    return False
                else:
                    text = await response.text()
                    _LOGGER.error("Failed to send command: %s - %s", response.status, text[:200])
                    return False
        except Exception as err:
            _LOGGER.error("Error sending command: %s", err)
            return False

    async def async_close(self) -> None:
        """Close the API session."""
        if self._session and not self._session.closed:
            await self._session.close()

    def get_cached_grills(self) -> list[dict]:
        """Get cached list of grills."""
        return self._grills
