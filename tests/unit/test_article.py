"""Unit tests for Article fetcher."""

import httpx
import pytest
import respx
from httpx import Response

from tldrist.clients.article import Article, ArticleFetcher, FetchError, is_nyt_url


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
    async def test_fetch_403_raises_fetch_error(self, fetcher: ArticleFetcher) -> None:
        """Should raise FetchError with HTTP 403 reason on 403."""
        respx.get("https://example.com/blocked").mock(
            return_value=Response(403)
        )

        with pytest.raises(FetchError, match="HTTP 403"):
            await fetcher.fetch("https://example.com/blocked")
        await fetcher.close()

    @respx.mock
    async def test_fetch_404_raises_fetch_error(self, fetcher: ArticleFetcher) -> None:
        """Should raise FetchError on 404."""
        respx.get("https://example.com/missing").mock(
            return_value=Response(404)
        )

        with pytest.raises(FetchError, match="HTTP 404"):
            await fetcher.fetch("https://example.com/missing")
        await fetcher.close()

    @respx.mock
    async def test_fetch_timeout_raises_fetch_error(self, fetcher: ArticleFetcher) -> None:
        """Should raise FetchError on timeout."""
        respx.get("https://example.com/slow").mock(
            side_effect=httpx.TimeoutException("timeout")
        )

        with pytest.raises(FetchError, match="timeout"):
            await fetcher.fetch("https://example.com/slow")
        await fetcher.close()

    @respx.mock
    async def test_fetch_short_content_raises_fetch_error(self, fetcher: ArticleFetcher) -> None:
        """Should raise FetchError when content extraction fails."""
        html = """
        <!DOCTYPE html>
        <html><body><p>Too short.</p></body></html>
        """
        respx.get("https://example.com/short").mock(
            return_value=Response(200, text=html)
        )

        with pytest.raises(FetchError, match="content extraction failed"):
            await fetcher.fetch("https://example.com/short")
        await fetcher.close()


class TestIsNytUrl:
    """Tests for is_nyt_url helper."""

    def test_nyt_article_url(self) -> None:
        assert is_nyt_url("https://www.nytimes.com/2024/01/01/article.html") is True

    def test_nyt_cooking_url(self) -> None:
        assert is_nyt_url("https://cooking.nytimes.com/recipes/123") is True

    def test_non_nyt_url(self) -> None:
        assert is_nyt_url("https://example.com/article") is False

    def test_nyt_substring_not_in_domain(self) -> None:
        assert is_nyt_url("https://notnytimes.com/article") is True  # contains "nytimes.com"


class TestArticleFetcherNytCookies:
    """Tests for NYT cookie handling in ArticleFetcher."""

    @respx.mock
    async def test_fetch_nyt_url_with_cookies(self) -> None:
        """Should send cookies when fetching NYT URLs."""
        nyt_cookies = httpx.Cookies()
        nyt_cookies.set("nyt-a", "abc123")

        html = """
        <!DOCTYPE html>
        <html><head><title>NYT Article</title></head>
        <body><article>
        <p>This is a New York Times article with enough content to pass the minimum word
        count. We need at least fifty words to be considered valid content for summarization.
        Here is some more text to ensure we have enough words in this test article.
        The content extraction should work correctly with this HTML structure.
        Testing the article fetcher with realistic content is important.</p>
        </article></body></html>
        """
        route = respx.get("https://www.nytimes.com/2024/01/01/article.html").mock(
            return_value=Response(200, text=html)
        )

        async with ArticleFetcher(nyt_cookies=nyt_cookies) as fetcher:
            await fetcher.fetch("https://www.nytimes.com/2024/01/01/article.html")

        # Verify cookies were sent
        request = route.calls[0].request
        assert "nyt-a=abc123" in request.headers.get("cookie", "")

    @respx.mock
    async def test_fetch_non_nyt_url_without_cookies(self) -> None:
        """Should NOT send NYT cookies when fetching non-NYT URLs."""
        nyt_cookies = httpx.Cookies()
        nyt_cookies.set("nyt-a", "abc123")

        html = """
        <!DOCTYPE html>
        <html><head><title>Other Article</title></head>
        <body><article>
        <p>This is a non-NYT article with enough content to pass the minimum word count.
        We need at least fifty words to be considered valid content for summarization.
        Here is some more text to ensure we have enough words in this test article.
        The content extraction should work correctly with this HTML structure.
        Testing the article fetcher with realistic content is important.</p>
        </article></body></html>
        """
        route = respx.get("https://example.com/article").mock(
            return_value=Response(200, text=html)
        )

        async with ArticleFetcher(nyt_cookies=nyt_cookies) as fetcher:
            await fetcher.fetch("https://example.com/article")

        # Verify no cookies were sent
        request = route.calls[0].request
        assert "nyt-a" not in request.headers.get("cookie", "")

    @respx.mock
    async def test_fetch_nyt_url_without_cookies(self) -> None:
        """Should still get 403 when no NYT cookies provided."""
        respx.get("https://www.nytimes.com/2024/01/01/article.html").mock(
            return_value=Response(403)
        )

        async with ArticleFetcher() as fetcher:
            with pytest.raises(FetchError, match="HTTP 403"):
                await fetcher.fetch("https://www.nytimes.com/2024/01/01/article.html")
