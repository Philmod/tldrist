"""Configuration loading for TLDRist."""

import re
from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Simple email regex - not exhaustive but catches obvious errors
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="TLDRIST_")

    # GCP settings
    gcp_project_id: str = Field(description="Google Cloud project ID")
    gcp_region: str = Field(default="europe-west1", description="Google Cloud region")

    # Todoist settings
    todoist_project_id: str = Field(description="ID of the Todoist project to process")

    # Email settings
    gmail_address: str = Field(description="Gmail address for sending emails")
    recipient_email: str = Field(description="Email address to receive the digest")

    # Secrets (injected by Cloud Run from Secret Manager, or set directly for local testing)
    todoist_token: str = Field(description="Todoist API token")
    gmail_app_password: str = Field(description="Gmail App Password")

    # Application settings
    log_level: str = Field(default="INFO", description="Logging level")
    dry_run: bool = Field(default=False, description="Run without sending email or updating tasks")
    skip_auth: bool = Field(default=False, description="Skip OIDC auth (local testing only)")

    @field_validator("gcp_project_id")
    @classmethod
    def validate_project_id(cls, v: str) -> str:
        """Validate GCP project ID is not empty."""
        if not v or not v.strip():
            raise ValueError(
                "TLDRIST_GCP_PROJECT_ID is required. "
                "Set it to your Google Cloud project ID."
            )
        return v.strip()

    @field_validator("gmail_address")
    @classmethod
    def validate_gmail_address(cls, v: str) -> str:
        """Validate Gmail address format."""
        if not v or not v.strip():
            raise ValueError(
                "TLDRIST_GMAIL_ADDRESS is required. "
                "Set it to the Gmail address used for sending digests."
            )
        v = v.strip()
        if not EMAIL_REGEX.match(v):
            raise ValueError(
                f"TLDRIST_GMAIL_ADDRESS '{v}' is not a valid email address."
            )
        return v

    @field_validator("recipient_email")
    @classmethod
    def validate_recipient_email(cls, v: str) -> str:
        """Validate recipient email format."""
        if not v or not v.strip():
            raise ValueError(
                "TLDRIST_RECIPIENT_EMAIL is required. "
                "Set it to the email address that should receive the digest."
            )
        v = v.strip()
        if not EMAIL_REGEX.match(v):
            raise ValueError(
                f"TLDRIST_RECIPIENT_EMAIL '{v}' is not a valid email address."
            )
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()  # type: ignore[call-arg]
