"""Summary generation service for TLDRist."""

from dataclasses import dataclass
from datetime import datetime, timezone

from tldrist.clients.article import Article
from tldrist.clients.gemini import ArticleSummary, GeminiClient
from tldrist.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ProcessedArticle:
    """Represents a fully processed article with summary."""

    task_id: str
    url: str
    title: str
    summary: str
    processed_at: datetime


class SummarizerService:
    """Service for generating article summaries."""

    def __init__(self, gemini_client: GeminiClient) -> None:
        self._gemini = gemini_client

    async def summarize(self, task_id: str, article: Article) -> ProcessedArticle:
        """Generate a summary for an article.

        Args:
            task_id: The Todoist task ID associated with this article.
            article: The extracted article content.

        Returns:
            A ProcessedArticle with the generated summary.
        """
        logger.info("Processing article", task_id=task_id, url=article.url)

        summary = await self._gemini.summarize_article(
            title=article.title,
            content=article.content,
        )

        return ProcessedArticle(
            task_id=task_id,
            url=article.url,
            title=article.title,
            summary=summary,
            processed_at=datetime.now(timezone.utc),
        )

    def format_task_description(self, processed: ProcessedArticle) -> str:
        """Format the summary for a Todoist task description.

        Args:
            processed: The processed article.

        Returns:
            Formatted description string for the Todoist task.
        """
        date_str = processed.processed_at.strftime("%Y-%m-%d")
        return f"""## Summary

{processed.summary}

---
*Processed by TLDRist on {date_str}*"""
