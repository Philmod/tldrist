"""Podcast generation service for TLDRist."""

import json
from datetime import UTC, datetime

from tldrist.clients.gemini import GeminiClient
from tldrist.clients.storage import ImageStorage
from tldrist.clients.tts import TTSClient
from tldrist.config import get_settings
from tldrist.services.summarizer import ProcessedArticle
from tldrist.utils.logging import get_logger

logger = get_logger(__name__)

PODCAST_SCRIPT_PROMPT = """You are a podcast script writer. Convert these article summaries into a \
natural, engaging conversation between two hosts named Alex and Sam.

Guidelines:
- Alex introduces topics and asks questions, Sam provides insights and reactions
- Keep it conversational and natural, like friends discussing interesting reads
- Include brief banter but stay informative
- Cover all articles, spending more time on the most interesting ones
- Start with a brief intro welcoming listeners to the weekly digest
- End with a sign-off thanking listeners and encouraging them to check out the articles
- Total length: {podcast_word_min}-{podcast_word_max} words (approximately {podcast_minutes_min}-{podcast_minutes_max} minutes when spoken)
- Format each line as: [ALEX]: text here  or  [SAM]: text here
- Do not include any stage directions or non-spoken text

Articles:
{articles_json}

Write the podcast script now:"""


class PodcastService:
    """Service for generating podcast audio from article summaries."""

    def __init__(self, gemini_client: GeminiClient) -> None:
        """Initialize the podcast service.

        Args:
            gemini_client: The Gemini client for script generation.
        """
        self._gemini = gemini_client

    async def generate_script(self, articles: list[ProcessedArticle]) -> str:
        """Generate a podcast script from article summaries.

        Args:
            articles: List of processed articles to discuss.

        Returns:
            The podcast script with speaker tags.
        """
        logger.info("Generating podcast script", article_count=len(articles))

        articles_data = [
            {"title": article.title, "url": article.url, "summary": article.summary}
            for article in articles
        ]
        articles_json = json.dumps(articles_data, indent=2)
        settings = get_settings()
        prompt = PODCAST_SCRIPT_PROMPT.format(
            articles_json=articles_json,
            podcast_word_min=settings.podcast_word_min,
            podcast_word_max=settings.podcast_word_max,
            podcast_minutes_min=settings.podcast_word_min // 100,
            podcast_minutes_max=settings.podcast_word_max // 100,
        )

        script = await self._gemini.generate_content(
            prompt,
            temperature=0.7,
            max_output_tokens=4096,
        )
        logger.info("Podcast script generated", script_length=len(script))
        return script

    async def generate_podcast(
        self,
        articles: list[ProcessedArticle],
        tts_client: TTSClient,
        storage: ImageStorage,
    ) -> str:
        """Generate a complete podcast and upload it to storage.

        Args:
            articles: List of processed articles to discuss.
            tts_client: The TTS client for audio synthesis.
            storage: The storage client for uploading.

        Returns:
            The public URL of the uploaded podcast.
        """
        logger.info("Starting podcast generation", article_count=len(articles))

        # Generate the script
        script = await self.generate_script(articles)

        # Synthesize the audio
        logger.info("Synthesizing podcast audio")
        audio_bytes = tts_client.synthesize_conversation(script)

        if not audio_bytes:
            logger.error("Failed to synthesize podcast audio")
            raise RuntimeError("Podcast audio synthesis failed")

        # Upload to storage
        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        podcast_url = storage.upload_podcast(audio_bytes, date_str)

        logger.info(
            "Podcast generation complete",
            url=podcast_url,
            audio_size=len(audio_bytes),
        )

        return podcast_url
