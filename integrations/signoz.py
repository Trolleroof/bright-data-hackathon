"""SigNoz via OTLP/HTTP. No keys → console spans. Setup does not open tickets."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from integrations.config import load_settings

_booted = False


def _boot() -> None:
    global _booted
    if _booted:
        return
    settings = load_settings()
    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.otel_service_name})
    )
    if settings.signoz_ready:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

        endpoint = settings.signoz_endpoint.rstrip("/")
        if not endpoint.endswith("/v1/traces"):
            endpoint = f"{endpoint}/v1/traces"
        exporter = OTLPSpanExporter(
            endpoint=endpoint,
            headers={"signoz-ingestion-key": settings.signoz_ingestion_key},
        )
        provider.add_span_processor(BatchSpanProcessor(exporter))
    # No keys: spans stay in-process. check_setup prints "console", not JSON dumps.
    trace.set_tracer_provider(provider)
    _booted = True


def tracer_ready() -> str:
    settings = load_settings()
    return "signoz" if settings.signoz_ready else "console"


def get_tracer():
    _boot()
    return trace.get_tracer("scaletwin")


@contextmanager
def span(name: str, **attrs: object) -> Iterator[None]:
    tracer = get_tracer()
    with tracer.start_as_current_span(name) as current:
        for key, value in attrs.items():
            current.set_attribute(key, value)
        yield


def smoke() -> str:
    """Emit the setup spans. Does not fire physical_prompt."""
    with span("detect", setup="true"):
        with span("tag_pose", setup="true"):
            with span("update_twin", setup="true"):
                pass
    provider = trace.get_tracer_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush(timeout_millis=5000)
    return tracer_ready()
