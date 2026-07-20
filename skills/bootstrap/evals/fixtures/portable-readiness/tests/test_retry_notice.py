from src.retry_notice import retry_notice


def test_duplicate_email_retry_is_suppressed() -> None:
    assert not retry_notice("reader@example.invalid", {"reader@example.invalid"})
