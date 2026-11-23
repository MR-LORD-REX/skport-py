from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from skport.errors import ConfigError


def retry_after_seconds(value: str | None) -> float | None:
    """Parse an HTTP Retry-After delay or date into nonnegative seconds."""
    if not value:
        return None
    try:
        delay = float(value)
        return max(0.0, delay) if math.isfinite(delay) else None
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bounded exponential backoff for the pipeline's safe retries."""

    attempts: int = 3
    backoff: float = 0.25
    max_backoff: float = 4.0
    jitter: float = 0.15

    def __post_init__(self) -> None:
        if isinstance(self.attempts, bool) or not isinstance(self.attempts, int) or self.attempts < 1:
            raise ConfigError("retry attempts must be a positive integer")
        for value in (self.backoff, self.max_backoff, self.jitter):
            if not math.isfinite(value) or value < 0:
                raise ConfigError("retry delays must be finite and nonnegative")

    def delay(self, attempt: int, retry_after: float | None = None) -> float:
        """Respect server pacing when it exceeds the local backoff."""
        base = min(self.max_backoff, self.backoff * (2 ** max(attempt - 1, 0)))
        return max(base + random.uniform(0, self.jitter), retry_after or 0.0)

    async def sleep(self, attempt: int, retry_after: float | None = None) -> None:
        """Pause before a retry; cancellation propagates to the caller."""
        await asyncio.sleep(self.delay(attempt, retry_after))
