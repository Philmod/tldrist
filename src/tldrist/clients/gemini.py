"""Vertex AI Gemini client for TLDRist."""

import json
from dataclasses import dataclass

import vertexai
from vertexai.generative_models import GenerationConfig, GenerativeModel, Part

from tldrist.config import SUMMARY_PARAGRAPHS
from tldrist.utils.logging import get_logger

logger = get_logger(__name__)

SUMMARIZE_PROMPT = """You are a helpful assistant that summarizes articles concisely.

Please provide a summary of the following article. The summary should:
- Be """ + SUMMARY_PARAGRAPHS + """ paragraphs long
- Capture the main points and key takeaways
- Be written in a clear, informative style
- Include any important facts, figures, or conclusions

Article Title: {title}

Article Content:
{content}

Summary:"""

DIGEST_PROMPT = """You are a helpful assistant creating a reading digest.

Based on the following article summaries, write a brief introduction (2-3 sentences) that highlights the main themes and most interesting insights.

Article Summaries:
{summaries}

Introduction:"""

SUMMARIZE_PDF_PROMPT = """You are a helpful assistant that summarizes academic papers concisely.

Please provide a summary of the following academic paper. The summary should:
- Be """ + SUMMARY_PARAGRAPHS + """ paragraphs long
- Explain the paper's main contributions and key findings
- Highlight the methodology and approach used
- Mention any important results, figures, or conclusions
- Be accessible to a technical but non-specialist audience

Paper Title: {title}

Summary:"""

EXTRACT_FIGURE_PROMPT = (
    "You are analyzing an academic paper to identify the most important "
    "figure or chart.\n\n"
    "Look through this paper and identify the single most important figure, "
    "chart, or diagram that best represents the paper's key contribution "
    "or findings.\n\n"
    "Respond with ONLY a JSON object in this format:\n"
    '{"figure_number": "1", "page_number": 3, '
    '"description": "Brief description of what the figure shows", '
    '"reason": "Why this figure is the most important"}\n\n'
    "If there are no figures, respond with:\n"
    '{"figure_number": null, "page_number": null, '
    '"description": null, "reason": "No figures found"}'
)


@dataclass
class FigureInfo:
    """Information about an identified important figure."""

    figure_number: str | None
    page_number: int | None
    description: str | None
    reason: str | None


@dataclass
class ArticleSummary:
    """Represents a summarized article."""

    url: str
    title: str
    summary: str


class GeminiClient:
    """Client for generating summaries using Vertex AI Gemini."""

    def __init__(
        self,
        project_id: str,
        region: str = "europe-west1",
        model_name: str = "gemini-2.0-flash-001",
    ) -> None:
        self._project_id = project_id
        self._region = region
        self._model_name = model_name
        self._initialized = False

    async def __aenter__(self) -> "GeminiClient":
        """Async context manager entry - initialize Vertex AI."""
        self._ensure_initialized()
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        """Async context manager exit - cleanup resources."""
        # Vertex AI client doesn't have explicit cleanup, but this ensures
        # the pattern is consistent and future-proof
        pass

    def _ensure_initialized(self) -> None:
        """Initialize Vertex AI if not already done."""
        if not self._initialized:
            vertexai.init(project=self._project_id, location=self._region)
            self._initialized = True
            logger.info("Vertex AI initialized", project=self._project_id, region=self._region)

    def _get_model(self) -> GenerativeModel:
        """Get the Gemini model instance."""
        self._ensure_initialized()
        return GenerativeModel(self._model_name)

    async def generate_content(
        self,
        prompt: str,
        *,
        temperature: float = 0.3,
        max_output_tokens: int = 1024,
    ) -> str:
        """Generate content with custom parameters.

        Args:
            prompt: The prompt to send to the model.
            temperature: Sampling temperature (0.0-1.0).
            max_output_tokens: Maximum tokens in response.

        Returns:
            The generated text.

        Raises:
            RuntimeError: If the model returns no content.
        """
        model = self._get_model()
        config = GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        response = await model.generate_content_async(prompt, generation_config=config)
        if not response.text:
            raise RuntimeError("Model returned empty response")
        return response.text

    async def summarize_article(self, title: str, content: str) -> str:
        """Generate a summary for an article.

        Args:
            title: The article title.
            content: The article content.

        Returns:
            The generated summary.
        """
        logger.info("Summarizing article", title=title)

        model = self._get_model()
        prompt = SUMMARIZE_PROMPT.format(title=title, content=content[:50000])

        config = GenerationConfig(
            temperature=0.3,
            max_output_tokens=1024,
        )

        response = await model.generate_content_async(prompt, generation_config=config)

        summary = response.text
        logger.info("Article summarized", title=title, summary_length=len(summary))
        return summary

    async def generate_digest_intro(self, summaries: list[ArticleSummary]) -> str:
        """Generate an introduction for the weekly digest.

        Args:
            summaries: List of article summaries.

        Returns:
            The digest introduction text.
        """
        logger.info("Generating digest introduction", article_count=len(summaries))

        model = self._get_model()

        summaries_text = "\n\n".join(
            f"**{s.title}**\n{s.summary}" for s in summaries
        )
        prompt = DIGEST_PROMPT.format(summaries=summaries_text)

        config = GenerationConfig(
            temperature=0.5,
            max_output_tokens=512,
        )

        response = await model.generate_content_async(prompt, generation_config=config)

        intro = response.text
        logger.info("Digest introduction generated", length=len(intro))
        return intro

    async def summarize_pdf(self, title: str, pdf_bytes: bytes) -> str:
        """Generate a summary for a PDF document.

        Args:
            title: The paper title.
            pdf_bytes: The PDF content as bytes.

        Returns:
            The generated summary.
        """
        logger.info("Summarizing PDF", title=title, pdf_size=len(pdf_bytes))

        model = self._get_model()

        pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")
        prompt = SUMMARIZE_PDF_PROMPT.format(title=title)

        config = GenerationConfig(
            temperature=0.3,
            max_output_tokens=2048,
        )

        response = await model.generate_content_async(
            [pdf_part, prompt],  # type: ignore[arg-type]
            generation_config=config,
        )

        summary = response.text
        logger.info("PDF summarized", title=title, summary_length=len(summary))
        return summary

    async def identify_important_figure(self, pdf_bytes: bytes) -> FigureInfo | None:
        """Identify the most important figure in a PDF.

        Args:
            pdf_bytes: The PDF content as bytes.

        Returns:
            FigureInfo with details about the most important figure, or None if failed.
        """
        logger.info("Identifying important figure", pdf_size=len(pdf_bytes))

        model = self._get_model()

        pdf_part = Part.from_data(data=pdf_bytes, mime_type="application/pdf")

        config = GenerationConfig(
            temperature=0.1,
            max_output_tokens=512,
        )

        try:
            response = await model.generate_content_async(
                [pdf_part, EXTRACT_FIGURE_PROMPT],  # type: ignore[arg-type]
                generation_config=config,
            )

            response_text = response.text.strip()
            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                lines = response_text.split("\n")
                response_text = "\n".join(lines[1:-1]) if len(lines) > 2 else response_text

            data = json.loads(response_text)

            figure_info = FigureInfo(
                figure_number=data.get("figure_number"),
                page_number=data.get("page_number"),
                description=data.get("description"),
                reason=data.get("reason"),
            )

            logger.info(
                "Figure identified",
                figure_number=figure_info.figure_number,
                page_number=figure_info.page_number,
            )
            return figure_info

        except json.JSONDecodeError as e:
            logger.warning("Failed to parse figure identification response", error=str(e))
            return None
        except Exception as e:
            logger.warning("Failed to identify important figure", error=str(e))
            return None
