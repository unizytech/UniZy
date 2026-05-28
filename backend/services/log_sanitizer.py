"""
Log Sanitizer Utility

Helpers to prevent PHI (Protected Health Information) from leaking into application logs.
Used across all service files for HIPAA-compliant logging.
"""


def truncate_id(value, length: int = 8) -> str:
    """Truncate an ID for safe logging. Returns first `length` chars + '...'"""
    if value is None:
        return "None"
    s = str(value)
    if len(s) <= length:
        return s
    return s[:length] + "..."


def safe_error(exception: Exception) -> str:
    """Return only the exception type name — no message that might contain PHI."""
    return type(exception).__name__
