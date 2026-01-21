"""Gmail SMTP email client for TLDRist."""

import re
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from tldrist.utils.logging import get_logger

logger = get_logger(__name__)

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465


class GmailClient:
    """Client for sending emails via Gmail SMTP."""

    def __init__(self, gmail_address: str, app_password: str) -> None:
        self._gmail_address = gmail_address
        self._app_password = app_password

    async def __aenter__(self) -> "GmailClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type | None, exc_val: BaseException | None, exc_tb: object) -> None:
        """Async context manager exit - cleanup resources."""
        # SMTP connections are created per-send, no persistent cleanup needed
        pass

    def send_email(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
    ) -> None:
        """Send an email via Gmail SMTP.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            html_content: HTML body of the email.
            text_content: Plain text body (optional, derived from HTML if not provided).
        """
        logger.info("Sending email", to=to, subject=subject)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self._gmail_address
        msg["To"] = to

        if text_content is None:
            text_content = self._html_to_text(html_content)

        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(self._gmail_address, self._app_password)
            server.sendmail(self._gmail_address, to, msg.as_string())

        logger.info("Email sent successfully", to=to)

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Convert HTML to plain text (basic conversion)."""
        text = re.sub(r"<br\s*/?>", "\n", html)
        text = re.sub(r"</p>", "\n\n", text)
        text = re.sub(r"</h[1-6]>", "\n\n", text)
        text = re.sub(r"</li>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
