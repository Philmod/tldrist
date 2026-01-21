"""Summary generation service for TLDRist."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import fitz  # PyMuPDF

from tldrist.clients.article import Article, ArxivContent
from tldrist.clients.gemini import GeminiClient
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
    image_data: bytes | None = field(default=None, repr=False)
    image_mime_type: str | None = None
    image_caption: str | None = None


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
            processed_at=datetime.now(UTC),
        )

    async def summarize_arxiv(
        self, task_id: str, arxiv_content: ArxivContent
    ) -> ProcessedArticle:
        """Generate a summary for an arXiv paper.

        Args:
            task_id: The Todoist task ID associated with this paper.
            arxiv_content: The fetched arXiv paper content.

        Returns:
            A ProcessedArticle with the generated summary and optional figure.
        """
        logger.info("Processing arXiv paper", task_id=task_id, url=arxiv_content.url)

        # Generate the summary using PDF
        summary = await self._gemini.summarize_pdf(
            title=arxiv_content.title,
            pdf_bytes=arxiv_content.pdf_bytes,
        )

        # Try to extract the most important figure
        image_data = None
        image_mime_type = None
        image_caption = None

        try:
            figure_info = await self._gemini.identify_important_figure(arxiv_content.pdf_bytes)
            if figure_info and figure_info.page_number is not None:
                image_data, image_mime_type = self._extract_figure_image(
                    arxiv_content.pdf_bytes, figure_info.page_number
                )
                if image_data and figure_info.description:
                    image_caption = figure_info.description
                    logger.info(
                        "Figure extracted",
                        task_id=task_id,
                        page=figure_info.page_number,
                        image_size=len(image_data),
                    )
        except Exception as e:
            logger.warning(
                "Failed to extract figure, continuing without image",
                task_id=task_id,
                error=str(e),
            )

        return ProcessedArticle(
            task_id=task_id,
            url=arxiv_content.url,
            title=arxiv_content.title,
            summary=summary,
            processed_at=datetime.now(UTC),
            image_data=image_data,
            image_mime_type=image_mime_type,
            image_caption=image_caption,
        )

    def _extract_figure_image(
        self, pdf_bytes: bytes, page_number: int
    ) -> tuple[bytes | None, str | None]:
        """Extract the largest image from a specific page of a PDF.

        Args:
            pdf_bytes: The PDF content as bytes.
            page_number: The 1-indexed page number to extract from.

        Returns:
            Tuple of (image_bytes, mime_type) or (None, None) if extraction fails.
        """
        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")

            # Convert to 0-indexed and handle out of range
            page_idx = page_number - 1
            if page_idx < 0 or page_idx >= len(doc):
                logger.warning(
                    "Page number out of range",
                    page_number=page_number,
                    total_pages=len(doc),
                )
                doc.close()
                return None, None

            page = doc[page_idx]
            images = page.get_images(full=True)

            if not images:
                logger.info("No images found on page", page_number=page_number)
                doc.close()
                return None, None

            # Find the largest image by area
            largest_image = None
            largest_area = 0

            for img_info in images:
                xref = img_info[0]
                base_image = doc.extract_image(xref)
                if base_image:
                    width = base_image.get("width", 0)
                    height = base_image.get("height", 0)
                    area = width * height
                    if area > largest_area:
                        largest_area = area
                        largest_image = base_image

            doc.close()

            if largest_image:
                image_bytes = largest_image["image"]
                ext = largest_image.get("ext", "png")
                mime_type = f"image/{ext}" if ext != "jpeg" else "image/jpeg"
                return image_bytes, mime_type

            return None, None

        except Exception as e:
            logger.warning("Failed to extract image from PDF", error=str(e))
            return None, None

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
*Processed by TL;DRist on {date_str}*"""
