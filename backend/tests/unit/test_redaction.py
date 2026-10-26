import pytest

from app.utils.redaction import REDACTED, redact_secrets, safe_error_message


@pytest.mark.parametrize(
    ("text", "secret"),
    [
        ("Authorization: Bearer abcdefghijklmnop123", "abcdefghijklmnop123"),
        ("request failed api_key=supersecretvalue", "supersecretvalue"),
        ('{"x-api-key": "k-123456789"}', "k-123456789"),
        ("password: hunter22", "hunter22"),
        ("used key sk-proj-ABCDEFGHIJKLMNOP1234", "sk-proj-ABCDEFGHIJKLMNOP1234"),
        ("google key AIzaSyA1234567890abcdefghijkl", "AIzaSyA1234567890abcdefghijkl"),
    ],
)
def test_secrets_are_redacted(text: str, secret: str) -> None:
    redacted = redact_secrets(text)
    assert secret not in redacted
    assert REDACTED in redacted


def test_ordinary_text_is_untouched() -> None:
    text = "rate limited by provider; retry after 2 seconds"
    assert redact_secrets(text) == text


def test_safe_error_message_truncates() -> None:
    message = safe_error_message("x" * 1000, max_length=50)
    assert len(message) == 50
    assert message.endswith("...")
