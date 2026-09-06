"""OpenTelemetry tracing configuration and application span helpers."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span

from app.database import engine
from app.settings import get_settings

SpanAttribute = str | int | float | bool


class Tracing:
    """Configure OTLP export and create FoodMind application spans."""

    def __init__(self) -> None:
        """Initialize tracing in an unconfigured state."""
        self._configured = False
        self._provider: TracerProvider | None = None

    def configure(self, app: FastAPI | None = None) -> None:
        """Configure one process-wide OpenTelemetry provider and instrumentors.

        Args:
            app: Optional FastAPI application to instrument. Background workers
                configure tracing without an HTTP application.
        """
        settings = get_settings()
        if self._configured or not settings.OTEL_ENABLED:
            return

        resource = Resource.create(
            {
                SERVICE_NAME: settings.OTEL_SERVICE_NAME,
                SERVICE_VERSION: "0.1.0",
            }
        )
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(
            endpoint=(f"{settings.OTEL_EXPORTER_OTLP_ENDPOINT.rstrip('/')}/v1/traces"),
            timeout=settings.OTEL_EXPORTER_OTLP_TIMEOUT_SECONDS,
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)

        if app is not None:
            FastAPIInstrumentor.instrument_app(app, excluded_urls="health,metrics")
        HTTPXClientInstrumentor().instrument()
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)

        self._configured = True
        self._provider = provider

    def shutdown(self) -> None:
        """Flush buffered spans before the API process exits."""
        if self._provider is not None:
            self._provider.force_flush()
            self._provider.shutdown()

    @contextmanager
    def span(
        self, name: str, attributes: Mapping[str, SpanAttribute] | None = None
    ) -> Iterator[Span]:
        """Create a child span with safe, low-cardinality attributes.

        Args:
            name: Stable operation name, for example ``foodmind.agent.execute``.
            attributes: Non-sensitive, bounded operation metadata.

        Yields:
            The active OpenTelemetry span.
        """
        with trace.get_tracer("foodmind").start_as_current_span(
            name, attributes=attributes
        ) as span:
            yield span


tracing = Tracing()
