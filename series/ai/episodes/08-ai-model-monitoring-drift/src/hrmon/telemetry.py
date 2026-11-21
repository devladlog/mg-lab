"""Telemetry: one structured log record per triage, plus quality and drift records, sent to Application Insights.

Python logging records with `extra=` become OpenTelemetry log records; the Microsoft OpenTelemetry Distro exports
them to Application Insights, where they land in the AppTraces table with the attributes in Properties.
The question text is never logged: only derived features and the model's answer.
"""
from __future__ import annotations

import logging
import re

LOGGER_NAME = "hrmon"
PREFIX = "hr_"
WINDOW = re.compile(r"^[A-Za-z0-9_.-]{1,40}$")      # also keeps window labels safe to put in a KQL string


def setup_azure_monitor(connection_string: str, credential) -> None:
    """Keyless export: the Application Insights resource has local auth disabled, so the exporter needs an Entra
    credential with Monitoring Metrics Publisher on it. Only the 'hrmon' logger is collected."""
    from microsoft.opentelemetry import use_microsoft_opentelemetry

    use_microsoft_opentelemetry(
        enable_azure_monitor=True,
        azure_monitor_connection_string=connection_string,
        azure_monitor_exporter_credential=credential,
        azure_monitor_enable_live_metrics=False,
        logger_name=LOGGER_NAME,
        enable_sensitive_data=False,   # GenAI instrumentation keeps prompt/response content out of spans
    )


def flush() -> None:
    """Short-lived scripts must flush: records are batched and a process that exits first loses them."""
    from opentelemetry import _logs

    provider = _logs.get_logger_provider()
    if hasattr(provider, "force_flush"):
        provider.force_flush()


def check_window(window: str) -> str:
    if not WINDOW.match(window or ""):
        raise ValueError(f"window label must match {WINDOW.pattern}: {window!r}")
    return window


def attributes(window: str, **values) -> dict:
    """Prefix every attribute so the records are easy to find and can't collide with standard properties."""
    out = {f"{PREFIX}window": check_window(window)}
    for k, v in values.items():
        if not isinstance(v, (str, bool, int, float)):
            raise TypeError(f"{k}: telemetry attributes must be str, bool, int or float")
        out[f"{PREFIX}{k}"] = v
    return out


def logger() -> logging.Logger:
    log = logging.getLogger(LOGGER_NAME)
    log.setLevel(logging.INFO)
    return log


def emit(message: str, attrs: dict) -> None:
    logger().info(message, extra=attrs)
