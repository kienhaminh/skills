def retry_notice(address: str, delivered: set[str]) -> bool:
    """Avoid sending a duplicate email when a delivery is retried."""
    return address not in delivered
