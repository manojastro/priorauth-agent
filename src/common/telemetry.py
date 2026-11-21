"""OpenTelemetry setup. Status: planned (stub). Real exporter wiring lands in M3.

Jaeger locally via OTLP; azure-monitor-opentelemetry behind AZURE_MONITOR_ENABLED.
"""

from src.common.config import Settings


def setup_telemetry(settings: Settings) -> bool:
    """Return True if telemetry was enabled. Currently a no-op unless enabled."""
    if not settings.otel_enabled:
        return False
    raise NotImplementedError("OTel exporter wiring is planned for M3")
