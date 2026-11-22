"""OpenTelemetry tracing setup for Resume Tailor.

Configures a tracer provider with a console exporter by default,
or an in-memory exporter when one is passed in (used by tests to
inspect the spans a run emits).
"""
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

_configured = False


def configure_tracing(exporter=None):
    """Set up the global tracer provider once.

    Args:
        exporter: A span exporter. Defaults to a console exporter.
            Pass an InMemorySpanExporter in tests to inspect spans.

    The first call wins; later calls are no-ops so the provider is
    never set twice in one process.
    """
    global _configured
    if _configured:
        return
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter or ConsoleSpanExporter()))
    trace.set_tracer_provider(provider)
    _configured = True


def get_tracer(name="resume-tailor"):
    """Return a tracer for the given instrumentation name."""
    return trace.get_tracer(name)
