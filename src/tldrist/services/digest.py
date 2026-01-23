"""Digest composition service for TLDRist."""

import html
from datetime import UTC, datetime

from tldrist.clients.gemini import ArticleSummary, GeminiClient
from tldrist.clients.storage import ImageStorage
from tldrist.services.summarizer import ProcessedArticle
from tldrist.utils.logging import get_logger

logger = get_logger(__name__)


class DigestService:
    """Service for composing the weekly digest email."""

    def __init__(
        self, gemini_client: GeminiClient, image_storage: ImageStorage | None = None
    ) -> None:
        self._gemini = gemini_client
        self._image_storage = image_storage

    async def compose_digest(
        self,
        articles: list[ProcessedArticle],
        podcast_url: str | None = None,
        web_page_url: str | None = None,
    ) -> tuple[str, str]:
        """Compose the weekly digest email.

        Args:
            articles: List of processed articles to include.
            podcast_url: Optional URL to the podcast audio file.
            web_page_url: Optional URL to the web page version of the digest.

        Returns:
            Tuple of (subject, html_content).
        """
        has_podcast = podcast_url is not None
        has_web_page = web_page_url is not None
        logger.info(
            "Composing digest",
            article_count=len(articles),
            has_podcast=has_podcast,
            has_web_page=has_web_page,
        )

        if not articles:
            return self._empty_digest()

        summaries = [
            ArticleSummary(url=a.url, title=a.title, summary=a.summary)
            for a in articles
        ]

        intro = await self._gemini.generate_digest_intro(summaries)
        subject = self._generate_subject()
        html = self._render_html(intro, articles, podcast_url, web_page_url)

        logger.info("Digest composed", subject=subject)
        return subject, html

    def _empty_digest(self) -> tuple[str, str]:
        """Generate an empty digest when there are no articles."""
        subject = self._generate_subject()
        html = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
<h1 style="color: #333;">tl;drist reading digest</h1>
<p>No articles were found in your Read list this week.</p>
<p>Add some articles to your Todoist "Read" project to receive summaries next week!</p>
</body>
</html>"""
        return subject, html

    def _generate_subject(self) -> str:
        """Generate the email subject line."""
        date_str = datetime.now(UTC).strftime("%B %d, %Y")
        return f"tl;drist reading digest - {date_str}"

    def _render_html(
        self,
        intro: str,
        articles: list[ProcessedArticle],
        podcast_url: str | None = None,
        web_page_url: str | None = None,
    ) -> str:
        """Render the digest as HTML."""
        # Escape intro text from LLM to prevent XSS
        safe_intro = html.escape(intro)
        articles_html = "\n".join(
            self._render_article(a) for a in articles
        )

        # Render podcast section if available
        podcast_html = ""
        if podcast_url:
            podcast_html = self._render_podcast_section(podcast_url)

        # Render web page link if available
        web_page_html = ""
        if web_page_url:
            safe_web_url = html.escape(web_page_url)
            web_page_html = f"""<div class="web-version">
<a href="{safe_web_url}">View this digest in your browser</a>
</div>"""

        return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 17px;
    max-width: 600px;
    margin: 0 auto;
    padding: 20px;
    color: #333;
    line-height: 1.7;
}}
h1 {{
    color: #1a1a1a;
    font-size: 26px;
    border-bottom: 2px solid #e0e0e0;
    padding-bottom: 10px;
}}
h2 {{
    color: #2c2c2c;
    font-size: 22px;
    margin-top: 30px;
    margin-bottom: 20px;
}}
p {{
    margin: 0 0 1em 0;
}}
.intro {{
    background: #f8f9fa;
    padding: 20px;
    border-radius: 8px;
    margin-bottom: 30px;
}}
.article {{
    margin-bottom: 40px;
    padding-bottom: 25px;
    border-bottom: 1px solid #e0e0e0;
}}
.article:last-child {{
    border-bottom: none;
}}
.article-title {{
    color: #1a73e8;
    text-decoration: none;
    font-size: 1.2em;
    font-weight: 600;
}}
.article-title:hover {{
    text-decoration: underline;
}}
.summary {{
    margin-top: 15px;
}}
.summary p {{
    margin-bottom: 1.2em;
}}
.figure-container {{
    margin: 15px 0;
    text-align: center;
}}
.article-figure {{
    max-width: 100%;
    height: auto;
    border: 1px solid #e0e0e0;
    border-radius: 4px;
}}
.figure-caption {{
    font-size: 0.9em;
    color: #666;
    margin-top: 8px;
    font-style: italic;
}}
.footer {{
    margin-top: 40px;
    padding-top: 20px;
    border-top: 1px solid #e0e0e0;
    font-size: 0.9em;
    color: #666;
}}
.podcast-section {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 20px;
    border-radius: 12px;
    margin-bottom: 30px;
    color: white;
}}
.podcast-section h3 {{
    margin: 0 0 10px 0;
    font-size: 1.1em;
}}
.podcast-section p {{
    margin: 0 0 15px 0;
    opacity: 0.9;
}}
.podcast-link {{
    display: inline-block;
    background: white;
    color: #667eea;
    padding: 10px 20px;
    border-radius: 25px;
    text-decoration: none;
    font-weight: 600;
}}
.podcast-link:hover {{
    opacity: 0.9;
}}
.web-version {{
    text-align: center;
    margin-bottom: 25px;
    padding: 15px;
    background: #f0f7ff;
    border-radius: 8px;
}}
.web-version a {{
    color: #1a73e8;
    text-decoration: none;
    font-weight: 500;
}}
.web-version a:hover {{
    text-decoration: underline;
}}
</style>
</head>
<body>
{web_page_html}

<h1>tl;drist reading digest</h1>

<div class="intro">
{safe_intro}
</div>

{podcast_html}

<h2>This Week's Articles</h2>

{articles_html}

<div class="footer">
<p>This digest was generated by TL;DRist using AI summarization.</p>
<p>Articles remain in your Todoist Read list with summaries added to their descriptions.</p>
</div>
</body>
</html>"""

    def _render_article(self, article: ProcessedArticle) -> str:
        """Render a single article as HTML."""
        # Escape all user/external content to prevent XSS
        safe_title = html.escape(article.title)
        safe_url = html.escape(article.url)
        safe_summary = html.escape(article.summary)
        summary_paragraphs = safe_summary.replace("\n\n", "</p><p>")

        # Upload and render image if present and storage is configured
        image_html = ""
        if article.image_data and article.image_mime_type and self._image_storage:
            try:
                image_url = self._image_storage.upload_image(
                    article.image_data,
                    article.image_mime_type,
                    article.task_id,
                )
                image_html = self._render_image(image_url, article.image_caption)
            except Exception as e:
                logger.warning(
                    "Failed to upload image, skipping",
                    task_id=article.task_id,
                    error=str(e),
                )

        return f"""<div class="article">
<a href="{safe_url}" class="article-title">{safe_title}</a>
<div class="summary">
<p>{summary_paragraphs}</p>
</div>
{image_html}
</div>"""

    def _render_image(self, image_url: str, caption: str | None) -> str:
        """Render an image from URL with optional caption.

        Args:
            image_url: The public URL of the image.
            caption: Optional caption for the image.

        Returns:
            HTML string for the figure container.
        """
        caption_html = ""
        if caption:
            safe_caption = html.escape(caption)
            caption_html = f'<p class="figure-caption">{safe_caption}</p>'

        return f"""<div class="figure-container">
<img src="{image_url}" class="article-figure" alt="Key figure from paper">
{caption_html}
</div>"""

    def _render_podcast_section(self, podcast_url: str) -> str:
        """Render the podcast section HTML.

        Args:
            podcast_url: The public URL of the podcast MP3.

        Returns:
            HTML string for the podcast section.
        """
        safe_url = html.escape(podcast_url)
        return f"""<div class="podcast-section">
<h3>Listen to This Week's Digest</h3>
<p>Hear Alex and Sam discuss this week's articles in our AI-generated podcast.</p>
<a href="{safe_url}" class="podcast-link">Listen Now</a>
</div>"""

    def render_web_html(
        self, intro: str, articles: list[ProcessedArticle], podcast_url: str | None = None
    ) -> str:
        """Render the digest as a web-friendly HTML page with Medium-like styling.

        This creates a more spacious, reader-friendly layout optimized for web viewing
        rather than email clients.

        Args:
            intro: The digest introduction text.
            articles: List of processed articles.
            podcast_url: Optional URL to the podcast audio file.

        Returns:
            HTML string for the web page.
        """
        safe_intro = html.escape(intro)
        articles_html = "\n".join(self._render_web_article(a) for a in articles)

        podcast_html = ""
        if podcast_url:
            podcast_html = self._render_web_podcast_section(podcast_url)

        date_str = datetime.now(UTC).strftime("%B %d, %Y")

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>tl;drist reading digest - {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,400;8..60,600;8..60,700&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
<style>
* {{
    box-sizing: border-box;
}}
body {{
    font-family: 'Source Serif 4', Georgia, 'Times New Roman', serif;
    font-size: 20px;
    line-height: 1.8;
    color: rgba(41, 41, 41, 1);
    background-color: #fff;
    margin: 0;
    padding: 0;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}}
.container {{
    max-width: 680px;
    margin: 0 auto;
    padding: 40px 24px 80px;
}}
header {{
    margin-bottom: 48px;
    padding-bottom: 32px;
    border-bottom: 1px solid rgba(230, 230, 230, 1);
}}
h1 {{
    font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 42px;
    font-weight: 700;
    line-height: 1.2;
    color: rgba(41, 41, 41, 1);
    margin: 0 0 16px 0;
    letter-spacing: -0.5px;
}}
.date {{
    font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 14px;
    color: rgba(117, 117, 117, 1);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
.intro {{
    font-size: 21px;
    line-height: 1.9;
    color: rgba(41, 41, 41, 0.9);
    margin-bottom: 48px;
    padding: 32px;
    background: rgba(250, 250, 250, 1);
    border-radius: 4px;
}}
h2 {{
    font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 28px;
    font-weight: 600;
    color: rgba(41, 41, 41, 1);
    margin: 56px 0 32px 0;
    letter-spacing: -0.3px;
}}
.article {{
    margin-bottom: 56px;
    padding-bottom: 48px;
    border-bottom: 1px solid rgba(230, 230, 230, 1);
}}
.article:last-child {{
    border-bottom: none;
    margin-bottom: 0;
    padding-bottom: 0;
}}
.article-title {{
    font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 24px;
    font-weight: 600;
    line-height: 1.4;
    color: rgba(41, 41, 41, 1);
    text-decoration: none;
    display: block;
    margin-bottom: 20px;
}}
.article-title:hover {{
    color: rgba(26, 137, 23, 1);
}}
.summary {{
    margin-top: 24px;
}}
.summary p {{
    margin: 0 0 24px 0;
}}
.summary p:last-child {{
    margin-bottom: 0;
}}
.figure-container {{
    margin: 32px 0;
    text-align: center;
}}
.article-figure {{
    max-width: 100%;
    height: auto;
    border-radius: 4px;
}}
.figure-caption {{
    font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 14px;
    color: rgba(117, 117, 117, 1);
    margin-top: 12px;
    font-style: normal;
    line-height: 1.5;
}}
.podcast-section {{
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    padding: 40px;
    border-radius: 8px;
    margin: 48px 0;
    color: white;
    text-align: center;
}}
.podcast-section h3 {{
    font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 24px;
    font-weight: 600;
    margin: 0 0 12px 0;
}}
.podcast-section p {{
    font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 16px;
    margin: 0 0 24px 0;
    opacity: 0.9;
}}
.podcast-link {{
    display: inline-block;
    background: white;
    color: #667eea;
    padding: 14px 32px;
    border-radius: 50px;
    text-decoration: none;
    font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-weight: 600;
    font-size: 16px;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
.podcast-link:hover {{
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}}
.footer {{
    margin-top: 64px;
    padding-top: 32px;
    border-top: 1px solid rgba(230, 230, 230, 1);
    font-family: 'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 14px;
    color: rgba(117, 117, 117, 1);
    text-align: center;
}}
.footer p {{
    margin: 8px 0;
    line-height: 1.6;
}}
@media (max-width: 680px) {{
    .container {{
        padding: 24px 20px 60px;
    }}
    h1 {{
        font-size: 32px;
    }}
    body {{
        font-size: 18px;
    }}
    .intro {{
        font-size: 19px;
        padding: 24px;
    }}
    h2 {{
        font-size: 24px;
        margin: 40px 0 24px 0;
    }}
    .article {{
        margin-bottom: 40px;
        padding-bottom: 32px;
    }}
    .article-title {{
        font-size: 20px;
    }}
    .podcast-section {{
        padding: 32px 24px;
    }}
}}
</style>
</head>
<body>
<div class="container">
<header>
<h1>tl;drist reading digest</h1>
<p class="date">{date_str}</p>
</header>

<div class="intro">
{safe_intro}
</div>

{podcast_html}

<h2>This Week's Articles</h2>

{articles_html}

<div class="footer">
<p>This digest was generated by TL;DRist using AI summarization.</p>
<p>Articles remain in your Todoist Read list with summaries added to their descriptions.</p>
</div>
</div>
</body>
</html>"""

    def _render_web_article(self, article: ProcessedArticle) -> str:
        """Render a single article as HTML for the web page."""
        safe_title = html.escape(article.title)
        safe_url = html.escape(article.url)
        safe_summary = html.escape(article.summary)
        summary_paragraphs = safe_summary.replace("\n\n", "</p><p>")

        image_html = ""
        if article.image_data and article.image_mime_type and self._image_storage:
            try:
                image_url = self._image_storage.upload_image(
                    article.image_data,
                    article.image_mime_type,
                    article.task_id,
                )
                image_html = self._render_web_image(image_url, article.image_caption)
            except Exception as e:
                logger.warning(
                    "Failed to upload image for web page, skipping",
                    task_id=article.task_id,
                    error=str(e),
                )

        return f"""<article class="article">
<a href="{safe_url}" class="article-title" target="_blank" rel="noopener">{safe_title}</a>
<div class="summary">
<p>{summary_paragraphs}</p>
</div>
{image_html}
</article>"""

    def _render_web_image(self, image_url: str, caption: str | None) -> str:
        """Render an image for the web page with optional caption."""
        caption_html = ""
        if caption:
            safe_caption = html.escape(caption)
            caption_html = f'<p class="figure-caption">{safe_caption}</p>'

        return f"""<div class="figure-container">
<img src="{image_url}" class="article-figure" alt="Key figure from paper" loading="lazy">
{caption_html}
</div>"""

    def _render_web_podcast_section(self, podcast_url: str) -> str:
        """Render the podcast section for the web page."""
        safe_url = html.escape(podcast_url)
        return f"""<div class="podcast-section">
<h3>Listen to This Week's Digest</h3>
<p>Hear Alex and Sam discuss this week's articles in our AI-generated podcast.</p>
<a href="{safe_url}" class="podcast-link">Listen Now</a>
</div>"""
