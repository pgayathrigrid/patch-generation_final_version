"""
Validation Report Builder.

Consumes ``SandboxValidationResult`` and produces a ``BuiltReport`` (rich
Python object) that can be serialised to JSON or Markdown via injectable
``ReportFormatter`` implementations.

Public surface
--------------
ReportBuilder          — abstract port (interface.py)
ReportFormatter        — abstract port (interface.py)
ValidationReportBuilder — concrete builder (builder.py)
JsonFormatter          — JSON serialiser (json_formatter.py)
MarkdownFormatter      — Markdown renderer (markdown_formatter.py)
BuiltReport            — rich report object (models.py)
AgentInfo              — agent identity sub-type (models.py)
ExecutionSummary       — execution context sub-type (models.py)
HookResult             — per-hook outcome sub-type (models.py)
ObservationSummary     — runtime observation sub-type (models.py)
ReportError            — error sub-type (models.py)
ReportWarning          — warning sub-type (models.py)
HookRecommendation     — recommendation sub-type (models.py)
"""
from awcp_instrumentation.application.reporter.builder import ValidationReportBuilder
from awcp_instrumentation.application.reporter.interface import ReportBuilder, ReportFormatter
from awcp_instrumentation.application.reporter.json_formatter import JsonFormatter
from awcp_instrumentation.application.reporter.markdown_formatter import MarkdownFormatter
from awcp_instrumentation.application.reporter.models import (
    AgentInfo,
    BuiltReport,
    ExecutionSummary,
    HookRecommendation,
    HookResult,
    ObservationSummary,
    ReportError,
    ReportWarning,
)

__all__ = [
    "ReportBuilder",
    "ReportFormatter",
    "ValidationReportBuilder",
    "JsonFormatter",
    "MarkdownFormatter",
    "BuiltReport",
    "AgentInfo",
    "ExecutionSummary",
    "HookResult",
    "ObservationSummary",
    "ReportError",
    "ReportWarning",
    "HookRecommendation",
]
