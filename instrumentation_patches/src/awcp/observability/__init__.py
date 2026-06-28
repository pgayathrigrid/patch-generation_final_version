"""
awcp.observability — OpenTelemetry setup helpers for AWCP-instrumented tools.

Usage::

    from awcp.observability import setup_otel, get_tracer

    setup_otel(service_name="my-awcp-tool")
    tracer = get_tracer()
    with tracer.start_as_current_span("my-stage"):
        ...

When ``opentelemetry-sdk`` is not installed, all functions are no-ops so the
tool runs without any observability dependency.
"""
from awcp.observability.setup import get_tracer, setup_otel

__all__ = ["setup_otel", "get_tracer"]
