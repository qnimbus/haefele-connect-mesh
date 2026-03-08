"""Date parsing utilities for the Häfele Connect Mesh API."""

from datetime import datetime

from ..exceptions import ValidationError


def parse_iso_date(date_str: str) -> datetime:
    """
    Parse an ISO 8601 formatted date string.

    Handles ISO 8601 dates with milliseconds and timezone indicator 'Z'.

    Args:
        date_str: ISO 8601 formatted date string (e.g., "2024-10-17T13:59:36.446Z")

    Returns:
        datetime: Parsed datetime object

    Raises:
        ValidationError: If the date string is invalid or cannot be parsed

    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        # Try without milliseconds if first attempt fails
        try:
            return datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError as e:
            raise ValidationError(
                f"Invalid date format: {date_str}. Expected ISO 8601 format."
            ) from e
