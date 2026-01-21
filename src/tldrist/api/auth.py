"""Authentication utilities for API endpoints."""

import os

from fastapi import Header, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from tldrist.config import get_settings
from tldrist.utils.logging import get_logger

logger = get_logger(__name__)


async def verify_oidc_token(
    authorization: str | None = Header(default=None),
) -> None:
    """Verify Cloud Scheduler OIDC token.

    This dependency validates that requests come from an authorized
    Cloud Scheduler job with a valid OIDC token.

    Args:
        authorization: The Authorization header containing the Bearer token.

    Raises:
        HTTPException: If the token is missing or invalid.
    """
    settings = get_settings()

    # Safety: Never skip auth in Cloud Run (K_SERVICE is always set by Cloud Run)
    is_cloud_run = os.environ.get("K_SERVICE") is not None
    if settings.skip_auth and not is_cloud_run:
        logger.warning("Skipping auth (local development mode)")
        return

    if not authorization:
        logger.warning("Missing authorization header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )

    if not authorization.startswith("Bearer "):
        logger.warning("Invalid authorization header format")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format",
        )

    token = authorization[7:]  # Remove "Bearer " prefix

    try:
        # Verify the OIDC token (signature and expiry)
        # Audience validation is handled by Cloud Run's IAM - only the scheduler
        # service account has roles/run.invoker permission
        request = google_requests.Request()
        claims: dict[str, object] = id_token.verify_oauth2_token(
            token, request, audience=None
        )  # type: ignore[no-untyped-call]

        # Log successful authentication (without sensitive data)
        logger.info(
            "OIDC token verified",
            email=claims.get("email", "unknown"),
            issuer=claims.get("iss", "unknown"),
        )
    except ValueError as e:
        logger.warning("Invalid OIDC token", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid OIDC token",
        ) from e
