"""
Rate limiting decorator for async API calls.

This module provides a decorator that implements rate limiting logic
for async API calls to prevent overloading the Häfele Connect Mesh API.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

T = TypeVar("T")
logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter tracking last call time for different function/instance combos."""

    def __init__(self):
        self._last_call_time: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, key: str) -> asyncio.Lock:
        """Get or create a lock for the given key."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    async def acquire(self, key: str, min_interval: float) -> None:
        """Acquire the rate limit lock and wait if needed."""
        lock = self.get_lock(key)
        await lock.acquire()
        try:
            # Check if we need to wait
            if key in self._last_call_time:
                elapsed = time.monotonic() - self._last_call_time[key]
                if elapsed < min_interval:
                    wait_time = min_interval - elapsed
                    logger.debug("Rate limit: waiting %.2f seconds", wait_time)
                    await asyncio.sleep(wait_time)

            self._last_call_time[key] = time.monotonic()
        finally:
            lock.release()


# Global rate limiter instance
_rate_limiter = RateLimiter()


def rate_limit(min_interval: float) -> Callable:
    """
    Decorator that implements rate limiting for async functions.

    Args:
        min_interval: Minimum time in seconds between function calls

    Returns:
        Callable: Decorated async function with rate limiting

    Example:
        @rate_limit(min_interval=1.0)
        async def api_call():
            return await make_request()

    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Create a unique key for this function call
            # If called on an instance method, include instance id
            if args and hasattr(args[0], "__class__"):
                key = f"{id(args[0])}:{func.__name__}"
            else:
                key = func.__name__

            await _rate_limiter.acquire(key, min_interval)
            return await func(*args, **kwargs)

        return wrapper

    return decorator
