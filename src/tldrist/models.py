"""Shared data models for TLDRist."""

from dataclasses import dataclass


@dataclass
class FailedArticle:
    """Represents an article that failed to fetch or process."""

    url: str
    reason: str
    task_id: str | None = None
    # Only permanent (article-specific) failures get a Todoist failure comment;
    # transient failures (e.g. Gemini outages) must stay retryable on later runs.
    permanent: bool = False
