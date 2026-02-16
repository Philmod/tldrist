"""Article fetcher and content extractor for TLDRist."""

import re
from dataclasses import dataclass

import httpx
import trafilatura
from readability import Document

from tldrist.utils.logging import get_logger

logger = get_logger(__name__)


class FetchError(Exception):
    """Raised when an article cannot be fetched or its content extracted."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

# ArXiv URL patterns
ARXIV_ABS_PATTERN = re.compile(r"https?://arxiv\.org/abs/(\d+\.\d+(?:v\d+)?)")
ARXIV_PDF_PATTERN = re.compile(r"https?://arxiv\.org/pdf/(\d+\.\d+(?:v\d+)?)")


def is_arxiv_url(url: str) -> bool:
    """Check if a URL is an arXiv abstract or PDF URL."""
    return bool(ARXIV_ABS_PATTERN.match(url) or ARXIV_PDF_PATTERN.match(url))


def arxiv_url_to_pdf_url(url: str) -> str:
    """Convert an arXiv URL to the PDF download URL.

    Args:
        url: An arXiv abstract or PDF URL.

    Returns:
        The PDF download URL.
    """
    abs_match = ARXIV_ABS_PATTERN.match(url)
    if abs_match:
        arxiv_id = abs_match.group(1)
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    pdf_match = ARXIV_PDF_PATTERN.match(url)
    if pdf_match:
        arxiv_id = pdf_match.group(1)
        return f"https://arxiv.org/pdf/{arxiv_id}.pdf"

    # If no pattern matches, return as-is (caller should validate first)
    return url


@dataclass
class ArxivContent:
    """Represents fetched arXiv paper content."""

    url: str
    pdf_url: str
    title: str
    pdf_bytes: bytes


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
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
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

    async def fetch(self, url: str) -> Article:
        """Fetch and extract content from a URL.

        Args:
            url: The URL to fetch.

        Returns:
            An Article object if extraction succeeds.

        Raises:
            FetchError: If the article cannot be fetched or content extraction fails.
        """
        logger.info("Fetching article", url=url)

        html = await self._fetch_html(url)

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
        raise FetchError("content extraction failed")

    async def _fetch_html(self, url: str) -> str:
        """Fetch HTML content from a URL.

        Raises:
            FetchError: If the HTTP request fails.
        """
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            logger.warning("HTTP error fetching URL", url=url, status=e.response.status_code)
            raise FetchError(f"HTTP {e.response.status_code}") from e
        except httpx.TimeoutException as e:
            logger.warning("Timeout fetching URL", url=url)
            raise FetchError("timeout") from e
        except httpx.RequestError as e:
            logger.warning("Request error fetching URL", url=url, error=str(e))
            raise FetchError(f"request error: {e}") from e

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

    async def fetch_arxiv(self, url: str) -> ArxivContent:
        """Fetch an arXiv paper as PDF.

        Args:
            url: The arXiv abstract or PDF URL.

        Returns:
            An ArxivContent object if successful.

        Raises:
            FetchError: If the paper cannot be fetched.
        """
        logger.info("Fetching arXiv paper", url=url)

        pdf_url = arxiv_url_to_pdf_url(url)

        try:
            # First fetch the abstract page to get the title
            abs_match = ARXIV_ABS_PATTERN.match(url)
            pdf_match = ARXIV_PDF_PATTERN.match(url)
            match = abs_match or pdf_match
            arxiv_id = match.group(1) if match else None

            if arxiv_id:
                abs_url = f"https://arxiv.org/abs/{arxiv_id}"
                abs_response = await self._client.get(abs_url)
                abs_response.raise_for_status()
                metadata = trafilatura.extract_metadata(abs_response.text)
                title = metadata.title if metadata and metadata.title else f"arXiv:{arxiv_id}"
            else:
                title = "arXiv Paper"

            # Fetch the PDF
            pdf_response = await self._client.get(pdf_url)
            pdf_response.raise_for_status()

            if "application/pdf" not in pdf_response.headers.get("content-type", ""):
                logger.warning("Response is not a PDF", url=pdf_url)
                raise FetchError("response is not a PDF")

            pdf_bytes = pdf_response.content

            logger.info(
                "arXiv paper fetched",
                url=url,
                title=title,
                pdf_size=len(pdf_bytes),
            )

            return ArxivContent(
                url=url,
                pdf_url=pdf_url,
                title=title,
                pdf_bytes=pdf_bytes,
            )

        except FetchError:
            raise
        except httpx.HTTPStatusError as e:
            logger.warning("HTTP error fetching arXiv", url=url, status=e.response.status_code)
            raise FetchError(f"HTTP {e.response.status_code}") from e
        except httpx.TimeoutException as e:
            logger.warning("Timeout fetching arXiv", url=url)
            raise FetchError("timeout") from e
        except httpx.RequestError as e:
            logger.warning("Request error fetching arXiv", url=url, error=str(e))
            raise FetchError(f"request error: {e}") from e
        except Exception as e:
            logger.error("Failed to fetch arXiv paper", url=url, error=str(e))
            raise FetchError(str(e)) from e
