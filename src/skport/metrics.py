from __future__ import annotations

import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass(slots=True)
class RequestMetric:
    """Timing and outcome for one completed request."""

    method: str
    path: str
    status: int | None
    seconds: float
    cache_hit: bool
    attempt: int
    unit: str | None


@dataclass(slots=True)
class Metrics:
    """Process-local counters with a bounded window of request samples."""

    counters: Counter[str] = field(default_factory=Counter)
    samples: list[RequestMetric] = field(default_factory=list)
    max_samples: int = 500

    def count(self, name: str, amount: int = 1) -> None:
        """Increment a named counter."""
        self.counters[name] += amount

    def record(self, metric: RequestMetric) -> None:
        """Store the newest request sample, discarding the oldest overflow."""
        self.samples.append(metric)
        if len(self.samples) > self.max_samples:
            del self.samples[: len(self.samples) - self.max_samples]

    @contextmanager
    def timer(self) -> Iterator[None]:
        """Measure a block into a millisecond counter."""
        started = time.perf_counter()
        try:
            yield
        finally:
            self.count("request_milliseconds_total", int((time.perf_counter() - started) * 1000))
