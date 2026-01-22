"""Pydantic models for API requests and responses."""

from pydantic import BaseModel, Field


class SummarizeResponse(BaseModel):
    """Response model for the summarize endpoint."""

    status: str = Field(description="Status of the operation")
    tasks_found: int = Field(description="Number of tasks found in the Read project")
    articles_processed: int = Field(description="Number of articles successfully processed")
    articles_failed: int = Field(description="Number of articles that failed to process")
    tasks_updated: int = Field(description="Number of Todoist tasks successfully updated")
    tasks_update_failed: int = Field(description="Number of Todoist tasks that failed to update")
    email_sent: bool = Field(description="Whether the digest email was sent")
    dry_run: bool = Field(description="Whether this was a dry run")
    skipped: bool = Field(default=False, description="Whether workflow was skipped due to min")


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: str = Field(description="Health status")
    version: str = Field(description="Application version")
