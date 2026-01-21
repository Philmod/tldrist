"""Unit tests for services."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from tldrist.clients.article import Article
from tldrist.clients.gemini import GeminiClient
from tldrist.services.summarizer import SummarizerService, ProcessedArticle
from tldrist.services.digest import DigestService


class TestSummarizerService:
    """Tests for SummarizerService."""

    @pytest.fixture
    def mock_gemini(self) -> MagicMock:
        """Create a mock Gemini client."""
        client = MagicMock(spec=GeminiClient)
        client.summarize_article = AsyncMock(return_value="This is a summary.")
        return client

    @pytest.fixture
    def service(self, mock_gemini: MagicMock) -> SummarizerService:
        """Create a service with mock client."""
        return SummarizerService(mock_gemini)

    async def test_summarize(self, service: SummarizerService, mock_gemini: MagicMock) -> None:
        """Should generate summary for article."""
        article = Article(
            url="https://example.com",
            title="Test Article",
            content="Article content here.",
            word_count=100,
        )

        result = await service.summarize("task-123", article)

        assert result.task_id == "task-123"
        assert result.url == "https://example.com"
        assert result.title == "Test Article"
        assert result.summary == "This is a summary."
        mock_gemini.summarize_article.assert_called_once()

    def test_format_task_description(self, service: SummarizerService) -> None:
        """Should format summary as task description."""
        processed = ProcessedArticle(
            task_id="123",
            url="https://example.com",
            title="Test",
            summary="This is the summary.",
            processed_at=datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        )

        description = service.format_task_description(processed)

        assert "## Summary" in description
        assert "This is the summary." in description
        assert "2024-01-15" in description
        assert "TL;DRist" in description


class TestDigestService:
    """Tests for DigestService."""

    @pytest.fixture
    def mock_gemini(self) -> MagicMock:
        """Create a mock Gemini client."""
        client = MagicMock(spec=GeminiClient)
        client.generate_digest_intro = AsyncMock(
            return_value="This week's digest covers interesting topics."
        )
        return client

    @pytest.fixture
    def service(self, mock_gemini: MagicMock) -> DigestService:
        """Create a service with mock client."""
        return DigestService(mock_gemini)

    async def test_compose_digest_empty(self, service: DigestService) -> None:
        """Should handle empty article list."""
        subject, html = await service.compose_digest([])

        assert "Weekly Reading Digest" in subject
        assert "No articles were found" in html

    async def test_compose_digest_with_articles(
        self, service: DigestService, mock_gemini: MagicMock
    ) -> None:
        """Should compose digest with articles."""
        articles = [
            ProcessedArticle(
                task_id="1",
                url="https://example.com/1",
                title="Article One",
                summary="Summary of article one.",
                processed_at=datetime.now(timezone.utc),
            ),
            ProcessedArticle(
                task_id="2",
                url="https://example.com/2",
                title="Article Two",
                summary="Summary of article two.",
                processed_at=datetime.now(timezone.utc),
            ),
        ]

        subject, html = await service.compose_digest(articles)

        assert "Weekly Reading Digest" in subject
        assert "Article One" in html
        assert "Article Two" in html
        assert "Summary of article one." in html
        assert "https://example.com/1" in html
        mock_gemini.generate_digest_intro.assert_called_once()
