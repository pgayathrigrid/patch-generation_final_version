"""
OTel setup and tracer accessor for the instrumentation tool itself.

The real opentelemetry-sdk is an optional dependency.  When it is absent,
setup_otel() is a no-op and get_tracer() returns a _NoOpTracer that supports
the same context-manager API so call sites need no ``if otel_enabled`` guards.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator, Optional


# ---------------------------------------------------------------------------
# No-op fallbacks (used when opentelemetry-sdk is not installed)
# ---------------------------------------------------------------------------

class _NoOpSpan:
    """Span stub — supports attribute setting and context-manager use."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def record_exception(self, exc: Exception) -> None:
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *_: Any) -> None:
        pass


class _NoOpTracer:
    @contextmanager
    def start_as_current_span(
        self, name: str, **_kwargs: Any
    ) -> Generator[_NoOpSpan, None, None]:
        yield _NoOpSpan()


_tracer: Any = _NoOpTracer()
_otel_enabled: bool = False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_otel(service_name: str, endpoint: Optional[str] = None) -> bool:
    """
    Initialise an OTLP tracer for *service_name*.

    Args:
        service_name: Logical name reported to the OTel collector.
        endpoint:     OTLP gRPC endpoint URL.  Defaults to
                      ``http://localhost:4317`` when ``None``.

    Returns:
        ``True`` if OTel was successfully configured, ``False`` if the SDK
        is not installed (the tool continues without tracing).
    """
    global _tracer, _otel_enabled
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint or "http://localhost:4317")
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
        _otel_enabled = True
        return True
    except ImportError:
        return False


def get_tracer(name: str = "awcp.instrumentation") -> Any:
    """Return the active tracer (real OTel tracer or no-op stub).

    The ``name`` parameter matches the signature of the real AWCP
    ``awcp.observability.setup.get_tracer(name)`` so both can be called
    identically regardless of which is in scope.
    """
    return _tracer
