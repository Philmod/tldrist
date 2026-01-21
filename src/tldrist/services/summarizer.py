"""Summary generation service for TLDRist."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import fitz  # PyMuPDF

from tldrist.clients.article import Article, ArxivContent
from tldrist.clients.gemini import FigureInfo, GeminiClient
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
                    arxiv_content.pdf_bytes, figure_info
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
        self, pdf_bytes: bytes, figure_info: FigureInfo
    ) -> tuple[bytes | None, str | None]:
        """Extract a figure from a PDF using multiple strategies.

        Strategies (in order of preference):
        1. Extract largest embedded raster image (most reliable for academic papers)
        2. Search for figure caption text and estimate region above it

        Args:
            pdf_bytes: The PDF content as bytes.
            figure_info: Information about the figure to extract.

        Returns:
            Tuple of (image_bytes, mime_type) or (None, None) if extraction fails.
        """
        page_number = figure_info.page_number
        if page_number is None:
            return None, None

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

            # Strategy 1: Extract largest embedded raster image (most reliable)
            result = self._extract_largest_raster_image(doc, page)
            if result[0]:
                logger.info(
                    "Using largest raster image",
                    page_number=page_number,
                )
                doc.close()
                return result

            # Strategy 2: Search for caption and estimate region
            if figure_info.figure_number:
                clip_rect = self._get_clip_rect_from_caption(page, figure_info.figure_number)
                if clip_rect:
                    image_bytes = self._render_clip_region(page, clip_rect)
                    if image_bytes:
                        logger.info(
                            "Estimated figure region from caption",
                            page_number=page_number,
                            figure_number=figure_info.figure_number,
                        )
                        doc.close()
                        return image_bytes, "image/png"

            logger.info("No images found on page", page_number=page_number)
            doc.close()
            return None, None

        except Exception as e:
            logger.warning("Failed to extract image from PDF", error=str(e))
            return None, None

    def _get_clip_rect_from_caption(
        self, page: fitz.Page, figure_number: str
    ) -> fitz.Rect | None:
        """Search for a figure caption and estimate the figure region above it.

        Args:
            page: The PDF page.
            figure_number: The figure number to search for (e.g., "1", "2a").

        Returns:
            A fitz.Rect for the estimated figure region, or None if not found.
        """
        import re

        # Search for common caption patterns
        patterns = [
            rf"Figure\s*{re.escape(figure_number)}[:\.\s]",
            rf"Fig\.\s*{re.escape(figure_number)}[:\.\s]",
            rf"FIGURE\s*{re.escape(figure_number)}[:\.\s]",
        ]

        text_instances = []
        for pattern in patterns:
            text_instances = page.search_for(pattern, quads=False)
            if text_instances:
                break

        if not text_instances:
            return None

        # Use the first match (typically the caption)
        caption_rect = text_instances[0]
        page_rect = page.rect

        # Estimate figure region: from top of page (or some margin) to just above caption
        # Add padding around the estimated region
        margin = 20  # pixels
        figure_top = max(page_rect.y0, caption_rect.y0 - page_rect.height * 0.4)
        figure_bottom = caption_rect.y0 - 5  # Small gap above caption

        # Use full page width with margins
        return fitz.Rect(
            page_rect.x0 + margin,
            figure_top,
            page_rect.x1 - margin,
            figure_bottom,
        )

    def _render_clip_region(
        self, page: fitz.Page, clip_rect: fitz.Rect, dpi: int = 150
    ) -> bytes | None:
        """Render a clipped region of a page as a PNG image.

        Args:
            page: The PDF page.
            clip_rect: The region to render.
            dpi: Resolution for rendering (default 150).

        Returns:
            PNG image bytes, or None if rendering fails.
        """
        try:
            # Calculate zoom factor for desired DPI (PDF default is 72 DPI)
            zoom = dpi / 72.0
            matrix = fitz.Matrix(zoom, zoom)

            # Render the clipped region
            pixmap = page.get_pixmap(matrix=matrix, clip=clip_rect)
            return pixmap.tobytes("png")
        except Exception as e:
            logger.warning("Failed to render clip region", error=str(e))
            return None

    def _extract_largest_raster_image(
        self, doc: fitz.Document, page: fitz.Page
    ) -> tuple[bytes | None, str | None]:
        """Extract the largest embedded raster image from a page.

        Args:
            doc: The PDF document.
            page: The PDF page.

        Returns:
            Tuple of (image_bytes, mime_type) or (None, None) if no images found.
        """
        images = page.get_images(full=True)

        if not images:
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

        if largest_image:
            image_bytes = largest_image["image"]
            ext = largest_image.get("ext", "png")
            mime_type = f"image/{ext}" if ext != "jpeg" else "image/jpeg"
            return image_bytes, mime_type

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
