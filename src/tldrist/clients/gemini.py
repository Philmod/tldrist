"""Vertex AI Gemini client for TLDRist."""

from dataclasses import dataclass

import vertexai
from vertexai.generative_models import GenerativeModel, GenerationConfig

from tldrist.utils.logging import get_logger

logger = get_logger(__name__)

SUMMARIZE_PROMPT = """You are a helpful assistant that summarizes articles concisely.

Please provide a summary of the following article. The summary should:
- Be 2-4 paragraphs long
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
