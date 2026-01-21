"""Article fetcher and content extractor for TLDRist."""

from dataclasses import dataclass

import httpx
import trafilatura
from readability import Document

from tldrist.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Article:
    """Represents an extracted article."""

    url: str
    title: str
    content: str
    word_count: int

    @property
    def is_valid(self) -> bool:
        """Check if the article has meaningful content."""
        return self.word_count >= 50


class ArticleFetcher:
    """Fetches and extracts content from article URLs."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; TLDRist/1.0; "
                    "+https://github.com/philmod/tldrist)"
                ),
            },
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "ArticleFetcher":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def fetch(self, url: str) -> Article | None:
        """Fetch and extract content from a URL.

        Args:
            url: The URL to fetch.

        Returns:
            An Article object if extraction succeeds, None otherwise.
        """
        logger.info("Fetching article", url=url)

        try:
            html = await self._fetch_html(url)
            if html is None:
                return None

            article = self._extract_content(url, html)
            if article and article.is_valid:
                logger.info(
                    "Article extracted",
                    url=url,
                    title=article.title,
                    word_count=article.word_count,
                )
                return article

            logger.warning("Article extraction failed or content too short", url=url)
            return None

        except Exception as e:
            logger.error("Failed to fetch article", url=url, error=str(e))
            return None

    async def _fetch_html(self, url: str) -> str | None:
        """Fetch HTML content from a URL."""
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            logger.warning("HTTP error fetching URL", url=url, status=e.response.status_code)
            return None
        except httpx.TimeoutException:
            logger.warning("Timeout fetching URL", url=url)
            return None
        except httpx.RequestError as e:
            logger.warning("Request error fetching URL", url=url, error=str(e))
            return None

    def _extract_content(self, url: str, html: str) -> Article | None:
        """Extract article content from HTML.

        Uses trafilatura as primary extractor, falls back to readability-lxml.
        """
        metadata = trafilatura.extract_metadata(html)
        title = metadata.title if metadata and metadata.title else ""

        content = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            no_fallback=False,
        )

        if not content or len(content.split()) < 50:
            logger.debug("Falling back to readability-lxml", url=url)
            content, title = self._extract_with_readability(html, title)

        if not content:
            return None

        word_count = len(content.split())
        if word_count < 50:
            return None

        return Article(url=url, title=title, content=content, word_count=word_count)

    def _extract_with_readability(self, html: str, fallback_title: str) -> tuple[str, str]:
        """Extract content using readability-lxml as fallback."""
        try:
            doc = Document(html)
            title = fallback_title or doc.title()
            content = trafilatura.utils.sanitize(doc.summary()) or ""
            return content, title
        except Exception as e:
            logger.debug("Readability extraction failed", error=str(e))
            return "", fallback_title
