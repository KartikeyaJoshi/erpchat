"""Structured JSON logging for node-level observability."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.observability.trace import get_trace_id

logger = logging.getLogger("erp_analyst_v2")


def configure_logging(level: int = logging.INFO) -> None:
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)


def log_event(
    event: str,
    node: str | None = None,
    *,
    latency_ms: float | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    payload: dict[str, Any] = {
        "event": event,
        "trace_id": get_trace_id(),
    }
    if node:
        payload["node"] = node
    if latency_ms is not None:
        payload["latency_ms"] = round(latency_ms, 2)
    if extra:
        payload.update(extra)
    logger.info(json.dumps(payload))


class NodeTimer:
    """Context manager for per-node latency logging."""

    def __init__(self, node: str, extra: dict[str, Any] | None = None):
        self.node = node
        self.extra = extra or {}
        self._start = 0.0

    def __enter__(self) -> "NodeTimer":
        self._start = time.perf_counter()
        log_event("node_start", self.node, extra=self.extra)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        elapsed = (time.perf_counter() - self._start) * 1000
        status = "node_error" if exc_type else "node_end"
        log_event(status, self.node, latency_ms=elapsed, extra=self.extra)
