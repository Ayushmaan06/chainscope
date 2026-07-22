"""Composable retry policy for network calls. Collectors take one as a constructor
argument (see docs/architecture.md) instead of inheriting shared retry behavior."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    """Retries a callable with exponential backoff.

    Every RPC/HTTP call in this codebase goes through one of these - free-tier
    providers rate-limit and occasionally drop connections, and a network call
    should not crash a collector on the first hiccup.
    """

    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    backoff_factor: float = 2.0
    retryable_exceptions: tuple[type[Exception], ...] = field(default=(Exception,))

    def run(self, fn: Callable[[], T]) -> T:
        """Calls `fn` with no arguments, retrying on `retryable_exceptions`."""
        delay = self.base_delay_seconds
        last_error: Exception | None = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                return fn()
            except self.retryable_exceptions as exc:
                last_error = exc
                if attempt == self.max_attempts:
                    break
                logger.warning(
                    "Attempt %d/%d failed (%s), retrying in %.1fs",
                    attempt,
                    self.max_attempts,
                    exc,
                    delay,
                )
                time.sleep(delay)
                delay *= self.backoff_factor

        assert last_error is not None
        raise last_error
