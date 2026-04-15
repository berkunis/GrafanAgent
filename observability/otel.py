"""Shared OTel bootstrap for every GrafanAgent service.

Usage:
    from observability import init_telemetry, get_tracer
    init_telemetry("router")
    tracer = get_tracer(__name__)

Reads OTEL_EXPORTER_OTLP_ENDPOINT to decide between OTLP (Grafana Cloud) and
stdout (local dev). Headers come from OTEL_EXPORTER_OTLP_HEADERS in the standard
"key1=val1,key2=val2" format.
"""
from __future__ import annotations

import logging
import os
import sys

import structlog
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)

_initialized = False


def init_telemetry(service_name: str) -> None:
    """Wire traces + metrics + structured logs. Safe to call multiple times."""
    global _initialized
    if _initialized:
        return

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "grafanagent",
            "deployment.environment": os.getenv("DEPLOY_ENV", "local"),
        }
    )

    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip()

    # --- Traces ---
    tracer_provider = TracerProvider(resource=resource)
    if otlp_endpoint:
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    else:
        tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    # --- Metrics ---
    if otlp_endpoint:
        metric_reader = PeriodicExportingMetricReader(OTLPMetricExporter())
    else:
        metric_reader = PeriodicExportingMetricReader(
            ConsoleMetricExporter(), export_interval_millis=60_000
        )
    metrics.set_meter_provider(
        MeterProvider(resource=resource, metric_readers=[metric_reader])
    )

    # --- Structured logs (JSON to stdout; Loki scrapes container stdout) ---
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )

    _initialized = True


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    return metrics.get_meter(name)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
