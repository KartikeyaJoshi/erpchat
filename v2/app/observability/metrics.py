"""In-memory baseline metrics for Phase 1 dashboards."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class MetricsSnapshot:
    total_requests: int = 0
    success_count: int = 0
    failed_count: int = 0
    validation_failures: int = 0
    db_failures: int = 0
    retry_total: int = 0
    latency_ms_sum: float = 0.0
    error_by_code: dict[str, int] = field(default_factory=dict)


class MetricsCollector:
    def __init__(self) -> None:
        self._lock = Lock()
        self._snapshot = MetricsSnapshot()
        self._error_counts: dict[str, int] = defaultdict(int)

    def record_request(
        self,
        *,
        status: str,
        latency_ms: float,
        error_code: str | None = None,
        validation_failed: bool = False,
        db_failed: bool = False,
        retry_count: int = 0,
    ) -> None:
        with self._lock:
            s = self._snapshot
            s.total_requests += 1
            s.latency_ms_sum += latency_ms
            s.retry_total += retry_count
            if status == "success":
                s.success_count += 1
            else:
                s.failed_count += 1
            if validation_failed:
                s.validation_failures += 1
            if db_failed:
                s.db_failures += 1
            if error_code:
                self._error_counts[error_code] += 1
                s.error_by_code = dict(self._error_counts)

    def snapshot(self) -> dict:
        with self._lock:
            s = self._snapshot
            avg_latency = (
                s.latency_ms_sum / s.total_requests if s.total_requests else 0.0
            )
            return {
                "total_requests": s.total_requests,
                "success_count": s.success_count,
                "failed_count": s.failed_count,
                "success_rate": (
                    s.success_count / s.total_requests if s.total_requests else 0.0
                ),
                "validation_failures": s.validation_failures,
                "db_failures": s.db_failures,
                "retry_total": s.retry_total,
                "avg_latency_ms": round(avg_latency, 2),
                "error_by_code": dict(s.error_by_code),
            }


metrics_collector = MetricsCollector()
