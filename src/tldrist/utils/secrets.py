"""Google Cloud Secret Manager wrapper for TLDRist."""

from functools import lru_cache

from google.cloud import secretmanager

from tldrist.utils.logging import get_logger

logger = get_logger(__name__)


class SecretManagerClient:
    """Client for accessing secrets from Google Cloud Secret Manager."""

    def __init__(self, project_id: str) -> None:
        self._project_id = project_id
        self._client = secretmanager.SecretManagerServiceClient()

    def get_secret(self, secret_id: str, version: str = "latest") -> str:
        """Retrieve a secret value from Secret Manager.

        Args:
            secret_id: The ID of the secret to retrieve.
            version: The version of the secret (default: "latest").

        Returns:
            The secret value as a string.
        """
        name = f"projects/{self._project_id}/secrets/{secret_id}/versions/{version}"
        logger.info("Accessing secret", secret_id=secret_id, version=version)

        response = self._client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")


@lru_cache(maxsize=1)
def get_secret_manager(project_id: str) -> SecretManagerClient:
    """Get or create a cached SecretManagerClient instance."""
    return SecretManagerClient(project_id)
