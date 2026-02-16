"""Shared data models for TLDRist."""

from dataclasses import dataclass


@dataclass
class FailedArticle:
    """Represents an article that failed to fetch or process."""

    url: str
    reason: str
