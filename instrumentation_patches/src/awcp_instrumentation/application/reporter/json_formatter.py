"""
Concrete formatter: JsonFormatter.

Serialises a ``BuiltReport`` to RFC 8259 JSON using ``dataclasses.asdict()``.

Datetime values are converted to ISO 8601 strings via a custom encoder.
``None`` values are preserved as JSON ``null``.  The output is pretty-printed
with 2-space indentation.

Adding a compact variant or a streaming variant would be done by implementing
a new ``ReportFormatter`` — this class is not modified.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime

from awcp_instrumentation.application.reporter.interface import ReportFormatter
from awcp_instrumentation.application.reporter.models import BuiltReport


class _DatetimeEncoder(json.JSONEncoder):
    """Encode ``datetime`` objects as ISO 8601 strings."""

    def default(self, obj: object) -> object:
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class JsonFormatter(ReportFormatter):
    """
    Serialises ``BuiltReport`` to pretty-printed JSON.

    Args:
        indent: Number of spaces for indentation (default: 2).
        ensure_ascii: When False, non-ASCII characters are output as-is.
    """

    def __init__(self, indent: int = 2, ensure_ascii: bool = False) -> None:
        self._indent = indent
        self._ensure_ascii = ensure_ascii

    @property
    def format_name(self) -> str:
        return "json"

    def format(self, report: BuiltReport) -> str:
        """Return *report* serialised as a JSON string."""
        data = dataclasses.asdict(report)
        return json.dumps(
            data,
            cls=_DatetimeEncoder,
            indent=self._indent,
            ensure_ascii=self._ensure_ascii,
        )
