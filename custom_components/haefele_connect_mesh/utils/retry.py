"""
Retry decorator with exponential backoff for async API calls.

This module provides a decorator that implements exponential backoff retry logic
for async API calls to the Häfele Connect Mesh API.
"""

import asyncio
import logging
import random
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from ..exceptions import HafeleAPIError, ValidationError

T = TypeVar("T")
logger = logging.getLogger(__name__)

# Status codes that should trigger a retry
RETRYABLE_STATUS_CODES: set[int] = {
    408,  # Request Timeout
    429,  # Too Many Requests
    500,  # Internal Server Error
    502,  # Bad Gateway
    503,  # Service Unavailable
    504,  # Gateway Timeout
}


def retry_with_backoff(
    max_attempts: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 16.0,
    jitter_range: float = 0.5,
) -> Callable:
    """
    Decorator that implements exponential backoff retry logic for async functions.

    Args:
        max_attempts: Maximum number of retry attempts (default: 5)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay in seconds (default: 16.0)
        jitter_range: Range of random jitter in seconds (default: ±0.5)

    Returns:
        Callable: Decorated async function with retry logic

    Example:
        @retry_with_backoff(max_attempts=3)
        async def api_call():
            return await make_request()

    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except (HafeleAPIError, ValidationError) as e:
                    last_exception = e

                    # Always retry on timeout
                    if isinstance(e, HafeleAPIError) and e.error_code == "TIMEOUT":
                        should_retry = True
                    # Retry on specific status codes
                    elif isinstance(e, HafeleAPIError) and e.status_code:
                        should_retry = e.status_code in RETRYABLE_STATUS_CODES
                    # Never retry validation errors
                    elif isinstance(e, ValidationError):
                        should_retry = False
                    else:
                        should_retry = False

                    if not should_retry:
                        logger.debug(
                            "Not retrying request. Error type: %s,"
                            " Status: %s, Code: %s",
                            type(e).__name__,
                            getattr(e, "status_code", None),
                            getattr(e, "error_code", None),
                        )
                        raise

                    if attempt == max_attempts - 1:
                        logger.warning(
                            "Max retry attempts (%d) reached. Last error: %s",
                            max_attempts,
                            str(e),
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                    # Add random jitter
                    jitter = random.uniform(-jitter_range, jitter_range)
                    total_delay = max(delay + jitter, base_delay)

                    logger.debug(
                        "Retrying request after %.2f seconds (attempt %d/%d)",
                        total_delay,
                        attempt + 1,
                        max_attempts,
                    )
                    await asyncio.sleep(total_delay)

            raise last_exception

        return wrapper

    return decorator
