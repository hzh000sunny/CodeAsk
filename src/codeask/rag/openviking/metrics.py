"""In-process OpenViking dashboard metrics."""

from __future__ import annotations

import asyncio
import math
import time
from collections import deque
from typing import Any


class OpenVikingMetricsRecorder:
    """Small in-memory latency recorder for OpenViking client calls."""

    def __init__(self, *, window_seconds: int = 300, cap: int = 1000) -> None:
        self._window_seconds = window_seconds
        self._latencies: deque[tuple[float, float]] = deque(maxlen=cap)
        self._lock = asyncio.Lock()

    async def record_latency(self, ms: float) -> None:
        async with self._lock:
            self._latencies.append((time.time(), max(0.0, ms)))

    def snapshot(self) -> dict[str, Any]:
        cutoff = time.time() - self._window_seconds
        samples = [latency for epoch, latency in self._latencies if epoch >= cutoff]
        if not samples:
            return {
                "collected": False,
                "window_seconds": self._window_seconds,
                "latency_p95_ms": None,
                "latency_samples": 0,
                "message": "warming up",
            }
        samples.sort()
        index = min(len(samples) - 1, max(0, math.ceil(len(samples) * 0.95) - 1))
        return {
            "collected": True,
            "window_seconds": self._window_seconds,
            "latency_p95_ms": int(round(samples[index])),
            "latency_samples": len(samples),
            "message": None,
        }
