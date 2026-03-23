"""Logging and metrics helpers."""

from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Any, Callable, TypeVar

from prometheus_client import Counter, Histogram, generate_latest

FUNCTION_CALLS = Counter(
    "tno_function_calls_total",
    "Total number of instrumented function calls",
    ["function", "status"],
)
FUNCTION_LATENCY = Histogram(
    "tno_function_latency_seconds",
    "Latency for instrumented functions",
    ["function"],
)

F = TypeVar("F", bound=Callable[..., Any])


def instrument(function_name: str | None = None) -> Callable[[F], F]:
    """Instrument a function with logging and Prometheus metrics."""

    def decorator(func: F) -> F:
        resolved_name = function_name or func.__name__

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = logging.getLogger("tno")
            start_time = time.perf_counter()
            logger.info("Entering %s", resolved_name)
            try:
                result = func(*args, **kwargs)
                FUNCTION_CALLS.labels(resolved_name, "success").inc()
                return result
            except Exception:
                FUNCTION_CALLS.labels(resolved_name, "failure").inc()
                logger.exception("Unhandled error in %s", resolved_name)
                raise
            finally:
                duration = time.perf_counter() - start_time
                FUNCTION_LATENCY.labels(resolved_name).observe(duration)
                logger.info("Exiting %s after %.4fs", resolved_name, duration)

        return wrapper  # type: ignore[return-value]

    return decorator


@instrument("render_metrics")
def render_metrics() -> bytes:
    """Expose Prometheus metrics."""

    return generate_latest()
