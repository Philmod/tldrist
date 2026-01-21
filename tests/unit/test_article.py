"""Unit tests for Article fetcher."""

import pytest
import respx
from httpx import Response

from tldrist.clients.article import Article, ArticleFetcher


class TestArticle:
    """Tests for Article data class."""

    def test_is_valid_with_enough_content(self) -> None:
        """Should be valid when word count is >= 50."""
        article = Article(
            url="https://example.com",
            title="Test",
            content=" ".join(["word"] * 50),
            word_count=50,
        )
        assert article.is_valid is True

    def test_is_invalid_with_little_content(self) -> None:
        """Should be invalid when word count is < 50."""
        article = Article(
            url="https://example.com",
            title="Test",
            content="short content",
            word_count=2,
        )
        assert article.is_valid is False


class TestArticleFetcher:
    """Tests for ArticleFetcher."""

    @pytest.fixture
    def fetcher(self) -> ArticleFetcher:
        """Create a test fetcher."""
        return ArticleFetcher()

    @respx.mock
    async def test_fetch_success(self, fetcher: ArticleFetcher) -> None:
        """Should fetch and extract article content."""
        html = """
        <!DOCTYPE html>
        <html>
        <head><title>Test Article</title></head>
        <body>
        <article>
        <h1>Test Article Title</h1>
        <p>This is a test article with enough content to pass the minimum word count.
        We need at least fifty words to be considered valid content for summarization.
        Here is some more text to ensure we have enough words in this test article.
        The content extraction should work correctly with this HTML structure.
        Testing the article fetcher with realistic content is important.</p>
        </article>
        </body>
        </html>
        """
        respx.get("https://example.com/article").mock(
            return_value=Response(200, text=html)
        )

        article = await fetcher.fetch("https://example.com/article")
        assert article is not None
        assert article.word_count >= 50
        await fetcher.close()

    @respx.mock
    async def test_fetch_404(self, fetcher: ArticleFetcher) -> None:
        """Should return None on 404."""
        respx.get("https://example.com/missing").mock(
            return_value=Response(404)
        )

        article = await fetcher.fetch("https://example.com/missing")
        assert article is None
        await fetcher.close()

    @respx.mock
    async def test_fetch_timeout(self, fetcher: ArticleFetcher) -> None:
        """Should return None on timeout."""
        import httpx

        respx.get("https://example.com/slow").mock(
            side_effect=httpx.TimeoutException("timeout")
        )

        article = await fetcher.fetch("https://example.com/slow")
        assert article is None
        await fetcher.close()

    @respx.mock
    async def test_fetch_short_content(self, fetcher: ArticleFetcher) -> None:
        """Should return None when content is too short."""
        html = """
        <!DOCTYPE html>
        <html><body><p>Too short.</p></body></html>
        """
        respx.get("https://example.com/short").mock(
            return_value=Response(200, text=html)
        )

        article = await fetcher.fetch("https://example.com/short")
        assert article is None
        await fetcher.close()
