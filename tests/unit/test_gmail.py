"""Unit tests for Gmail client."""

from unittest.mock import MagicMock, patch

from tldrist.clients.gmail import GmailClient


class TestGmailClient:
    """Tests for GmailClient."""

    def test_html_to_text(self) -> None:
        """Should convert HTML to plain text."""
        html = "<h1>Title</h1><p>Paragraph one.</p><p>Paragraph two.</p>"
        text = GmailClient._html_to_text(html)
        assert "Title" in text
        assert "Paragraph one." in text
        assert "Paragraph two." in text
        assert "<" not in text

    def test_html_to_text_with_br(self) -> None:
        """Should convert <br> tags to newlines."""
        html = "Line one<br>Line two<br/>Line three"
        text = GmailClient._html_to_text(html)
        assert "Line one\nLine two\nLine three" in text

    @patch("tldrist.clients.gmail.smtplib.SMTP_SSL")
    def test_send_email(self, mock_smtp_class: MagicMock) -> None:
        """Should send email via SMTP."""
        mock_smtp = MagicMock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp

        client = GmailClient("sender@gmail.com", "app-password")
        client.send_email(
            to="recipient@example.com",
            subject="Test Subject",
            html_content="<p>Test body</p>",
        )

        mock_smtp.login.assert_called_once_with("sender@gmail.com", "app-password")
        mock_smtp.sendmail.assert_called_once()

        call_args = mock_smtp.sendmail.call_args
        assert call_args[0][0] == "sender@gmail.com"
        assert call_args[0][1] == "recipient@example.com"
        assert "Test Subject" in call_args[0][2]
