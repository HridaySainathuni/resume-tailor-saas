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


def attach_exporter(exporter):
    """Attach another span exporter to the tracer provider.

    When tracing is not configured yet, this configures it with
    the given exporter. When it is already configured (for example
    by a test module), the exporter is added as a second span
    processor so its spans are captured too.

    Args:
        exporter: A span exporter, such as an InMemorySpanExporter.
    """
    global _configured
    if not _configured:
        configure_tracing(exporter=exporter)
        return
    provider = trace.get_tracer_provider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))


def get_tracer(name="resume-tailor"):
    """Return a tracer for the given instrumentation name."""
    return trace.get_tracer(name)
