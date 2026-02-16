"""Unit tests for DigestService failure footnotes."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from tldrist.clients.gemini import GeminiClient
from tldrist.models import FailedArticle
from tldrist.services.digest import DigestService
from tldrist.services.summarizer import ProcessedArticle


class TestDigestFailuresFootnote:
    """Tests for the failures footnote rendering."""

    @pytest.fixture
    def service(self) -> DigestService:
        gemini = MagicMock(spec=GeminiClient)
        gemini.generate_digest_intro = AsyncMock(return_value="Intro text.")
        return DigestService(gemini)

    def test_failures_footnote_renders_correctly(self, service: DigestService) -> None:
        """Failures footnote should list each URL and its error reason."""
        failed = [
            FailedArticle(url="https://nyt.com/article", reason="HTTP 403"),
            FailedArticle(url="https://ibm.com/dev", reason="content extraction failed"),
        ]

        html = service._render_failures_footnote(failed)

        assert "Failed to fetch (2)" in html
        assert "https://nyt.com/article" in html
        assert "HTTP 403" in html
        assert "https://ibm.com/dev" in html
        assert "content extraction failed" in html

    def test_failures_footnote_empty_when_no_failures(self, service: DigestService) -> None:
        """No footnote when there are no failures."""
        assert service._render_failures_footnote(None) == ""
        assert service._render_failures_footnote([]) == ""

    async def test_empty_articles_with_failures_produces_footnote(
        self, service: DigestService
    ) -> None:
        """Empty digest with failed articles should include the failures footnote."""
        failed = [
            FailedArticle(url="https://example.com/broken", reason="HTTP 403"),
        ]

        subject, html = await service.compose_digest([], failed_articles=failed)

        assert "tl;drist reading digest" in subject
        assert "No articles were found" in html
        assert "Failed to fetch (1)" in html
        assert "https://example.com/broken" in html
        assert "HTTP 403" in html

    async def test_digest_with_articles_and_failures(self, service: DigestService) -> None:
        """Digest with both successful and failed articles should include footnote."""
        articles = [
            ProcessedArticle(
                task_id="1",
                url="https://example.com/ok",
                title="Good Article",
                summary="A good summary.",
                processed_at=datetime.now(timezone.utc),
            ),
        ]
        failed = [
            FailedArticle(url="https://example.com/bad", reason="timeout"),
        ]

        subject, html = await service.compose_digest(articles, failed_articles=failed)

        assert "Good Article" in html
        assert "A good summary." in html
        assert "Failed to fetch (1)" in html
        assert "https://example.com/bad" in html
        assert "timeout" in html
