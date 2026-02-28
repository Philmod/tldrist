"""Unit tests for NYT authentication client."""

import httpx
import pytest
import respx
from httpx import Response

from tldrist.clients.nyt import NYT_AUTH_BASE, NytAuthError, NytClient


class TestNytClient:
    """Tests for NytClient."""

    @pytest.fixture
    def email(self) -> str:
        return "test@example.com"

    @pytest.fixture
    def password(self) -> str:
        return "test-password"

    @respx.mock
    async def test_login_success(self, email: str, password: str) -> None:
        """Should return cookies after successful two-step login."""
        respx.post(f"{NYT_AUTH_BASE}/authorize-email").mock(
            return_value=Response(200, json={"status": "ok"})
        )
        respx.post(f"{NYT_AUTH_BASE}/login").mock(
            return_value=Response(
                200,
                json={"status": "ok"},
                headers={"set-cookie": "nyt-a=abc123; Path=/"},
            )
        )

        async with NytClient(email, password) as nyt:
            cookies = await nyt.get_cookies()
            assert cookies is not None
            assert len(cookies) > 0

    @respx.mock
    async def test_login_caches_cookies(self, email: str, password: str) -> None:
        """Should only call login endpoints once, returning cached cookies on second call."""
        auth_route = respx.post(f"{NYT_AUTH_BASE}/authorize-email").mock(
            return_value=Response(200, json={"status": "ok"})
        )
        login_route = respx.post(f"{NYT_AUTH_BASE}/login").mock(
            return_value=Response(
                200,
                json={"status": "ok"},
                headers={"set-cookie": "nyt-a=abc123; Path=/"},
            )
        )

        async with NytClient(email, password) as nyt:
            cookies1 = await nyt.get_cookies()
            cookies2 = await nyt.get_cookies()
            assert cookies1 is cookies2
            assert auth_route.call_count == 1
            assert login_route.call_count == 1

    @respx.mock
    async def test_authorize_email_failure(self, email: str, password: str) -> None:
        """Should raise NytAuthError when authorize-email returns 400."""
        respx.post(f"{NYT_AUTH_BASE}/authorize-email").mock(
            return_value=Response(400, json={"error": "bad request"})
        )

        async with NytClient(email, password) as nyt:
            with pytest.raises(NytAuthError, match="authorize-email failed"):
                await nyt.get_cookies()

    @respx.mock
    async def test_login_failure(self, email: str, password: str) -> None:
        """Should raise NytAuthError when login returns 401."""
        respx.post(f"{NYT_AUTH_BASE}/authorize-email").mock(
            return_value=Response(200, json={"status": "ok"})
        )
        respx.post(f"{NYT_AUTH_BASE}/login").mock(
            return_value=Response(401, json={"error": "unauthorized"})
        )

        async with NytClient(email, password) as nyt:
            with pytest.raises(NytAuthError, match="login failed"):
                await nyt.get_cookies()

    @respx.mock
    async def test_no_cookies_returned(self, email: str, password: str) -> None:
        """Should raise NytAuthError when login succeeds but no cookies are set."""
        respx.post(f"{NYT_AUTH_BASE}/authorize-email").mock(
            return_value=Response(200, json={"status": "ok"})
        )
        respx.post(f"{NYT_AUTH_BASE}/login").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        async with NytClient(email, password) as nyt:
            with pytest.raises(NytAuthError, match="no cookies returned"):
                await nyt.get_cookies()

    @respx.mock
    async def test_network_error(self, email: str, password: str) -> None:
        """Should raise NytAuthError on connection error."""
        respx.post(f"{NYT_AUTH_BASE}/authorize-email").mock(
            side_effect=httpx.ConnectError("connection refused")
        )

        async with NytClient(email, password) as nyt:
            with pytest.raises(NytAuthError, match="network error"):
                await nyt.get_cookies()
