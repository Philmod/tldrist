"""Vertex AI Gemini client for TLDRist."""

import json
from dataclasses import dataclass

from google import genai
from google.genai.types import (
    FinishReason,
    GenerateContentConfig,
    GenerateContentResponse,
    Part,
    ThinkingConfig,
    ThinkingLevel,
)

from tldrist.config import get_settings
from tldrist.utils.logging import get_logger

logger = get_logger(__name__)

SUMMARIZE_PROMPT = """You are a helpful assistant that summarizes articles concisely.

Please provide a summary of the following article. The summary should:
- Be {summary_paragraphs} paragraphs long
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
- Be {summary_paragraphs} paragraphs long
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

# Summarization doesn't need deep reasoning, and thinking tokens share the
# max_output_tokens budget: with thinking at MINIMAL the cap bounds visible
# text again, so summary length is controlled by the prompt, not truncation.
THINKING_CONFIG = ThinkingConfig(thinking_level=ThinkingLevel.MINIMAL)


def _response_text(response: GenerateContentResponse) -> str:
    """Extract text from a Gemini response, rejecting truncated output.

    A response that hit max_output_tokens is cut off mid-sentence; raising
    turns that into a retryable failure instead of shipping a cut-off summary.
    """
    candidates = response.candidates
    if candidates and candidates[0].finish_reason == FinishReason.MAX_TOKENS:
        raise RuntimeError(
            "Model response truncated (hit max_output_tokens before finishing)"
        )
    text = response.text
    if not text:
        raise RuntimeError("Model returned empty response")
    return text


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
        region: str = "global",
        model_name: str = "gemini-3.5-flash",
    ) -> None:
        self._project_id = project_id
        self._region = region
        self._model_name = model_name
        self._client: genai.Client | None = None

    async def __aenter__(self) -> "GeminiClient":
        """Async context manager entry - initialize the client."""
        self._get_client()
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        """Async context manager exit - close the underlying HTTP client."""
        if self._client is not None:
            await self._client.aio.aclose()
            self._client = None

    def _get_client(self) -> genai.Client:
        """Get the Gemini client, creating it on first use."""
        if self._client is None:
            self._client = genai.Client(
                vertexai=True, project=self._project_id, location=self._region
            )
            logger.info(
                "Gemini client initialized", project=self._project_id, location=self._region
            )
        return self._client

    async def _generate(
        self,
        contents: str | list[Part | str],
        *,
        temperature: float,
        max_output_tokens: int,
    ) -> str:
        """Run a generation request and return the validated text."""
        client = self._get_client()
        response = await client.aio.models.generate_content(
            model=self._model_name,
            contents=contents,
            config=GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                thinking_config=THINKING_CONFIG,
            ),
        )
        return _response_text(response)

    async def generate_content(
        self,
        prompt: str,
        *,
        temperature: float = 0.3,
        max_output_tokens: int = 2048,
    ) -> str:
        """Generate content with custom parameters.

        Args:
            prompt: The prompt to send to the model.
            temperature: Sampling temperature (0.0-1.0).
            max_output_tokens: Maximum tokens in response.

        Returns:
            The generated text.

        Raises:
            RuntimeError: If the model returns no content or truncated content.
        """
        return await self._generate(
            prompt, temperature=temperature, max_output_tokens=max_output_tokens
        )

    async def summarize_article(self, title: str, content: str) -> str:
        """Generate a summary for an article.

        Args:
            title: The article title.
            content: The article content.

        Returns:
            The generated summary.
        """
        logger.info("Summarizing article", title=title)

        settings = get_settings()
        prompt = SUMMARIZE_PROMPT.format(
            title=title, content=content[:50000],
            summary_paragraphs=settings.summary_paragraphs,
        )

        summary = await self._generate(prompt, temperature=0.3, max_output_tokens=2048)
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

        summaries_text = "\n\n".join(
            f"**{s.title}**\n{s.summary}" for s in summaries
        )
        prompt = DIGEST_PROMPT.format(summaries=summaries_text)

        intro = await self._generate(prompt, temperature=0.5, max_output_tokens=1024)
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

        pdf_part = Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
        settings = get_settings()
        prompt = SUMMARIZE_PDF_PROMPT.format(
            title=title, summary_paragraphs=settings.summary_paragraphs,
        )

        summary = await self._generate(
            [pdf_part, prompt], temperature=0.3, max_output_tokens=2048
        )
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

        pdf_part = Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")

        try:
            response_text = await self._generate(
                [pdf_part, EXTRACT_FIGURE_PROMPT],
                temperature=0.1,
                max_output_tokens=1024,
            )

            response_text = response_text.strip()
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
