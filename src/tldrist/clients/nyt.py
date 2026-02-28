"""NYT subscriber authentication client for TLDRist."""

import httpx

from tldrist.utils.logging import get_logger

logger = get_logger(__name__)

NYT_AUTH_BASE = "https://myaccount.nytimes.com/svc/lire_ui"


class NytAuthError(Exception):
    """Raised when NYT authentication fails."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class NytClient:
    """Client that authenticates with NYT to obtain session cookies."""

    def __init__(self, email: str, password: str) -> None:
        self._email = email
        self._password = password
        self._client = httpx.AsyncClient(follow_redirects=True, timeout=30.0)
        self._cookies: httpx.Cookies | None = None

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "NytClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def get_cookies(self) -> httpx.Cookies:
        """Perform lazy login and return session cookies (cached after first call).

        Raises:
            NytAuthError: If authentication fails.
        """
        if self._cookies is not None:
            return self._cookies

        try:
            # Step 1: Authorize email
            resp = await self._client.post(
                f"{NYT_AUTH_BASE}/authorize-email",
                json={"email": self._email},
            )
            if not resp.is_success:
                raise NytAuthError(f"authorize-email failed: HTTP {resp.status_code}")

            # Step 2: Login with password
            resp = await self._client.post(
                f"{NYT_AUTH_BASE}/login",
                json={"email": self._email, "password": self._password},
            )
            if not resp.is_success:
                raise NytAuthError(f"login failed: HTTP {resp.status_code}")

        except NytAuthError:
            raise
        except httpx.RequestError as e:
            raise NytAuthError(f"network error: {e}") from e

        if not self._client.cookies:
            raise NytAuthError("no cookies returned after login")

        self._cookies = httpx.Cookies(self._client.cookies)
        logger.info("NYT login successful")
        return self._cookies
