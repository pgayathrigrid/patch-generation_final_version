"""
Abstract ports for the Validation Report Builder.

ReportFormatter — extension point for output formats (JSON, Markdown, …)
ReportBuilder   — contract for building a BuiltReport from a SandboxValidationResult

Adding a new format (HTML, PDF, dashboard serialization) means implementing
``ReportFormatter`` — no existing code changes.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from awcp_instrumentation.application.reporter.models import BuiltReport
from awcp_instrumentation.application.sandbox.models import SandboxValidationResult


class ReportFormatter(ABC):
    """
    Port: serialises a ``BuiltReport`` to a string in a specific format.

    Concrete implementations:
        JsonFormatter     — RFC 8259 JSON, pretty-printed
        MarkdownFormatter — GitHub-Flavoured Markdown
        [future] HtmlFormatter, PdfFormatter, DashboardFormatter
    """

    @abstractmethod
    def format(self, report: BuiltReport) -> str:
        """
        Serialise *report* to a string.

        Args:
            report: The assembled report produced by ``ReportBuilder.build()``.

        Returns:
            String representation of the report in this formatter's target format.
        """

    @property
    @abstractmethod
    def format_name(self) -> str:
        """
        Short identifier for this format (e.g. ``"json"``, ``"markdown"``).

        Used for file-extension selection and logging.
        """


class ReportBuilder(ABC):
    """
    Port: assembles a ``BuiltReport`` from a ``SandboxValidationResult``.

    There is one natural implementation (``ValidationReportBuilder``), but
    the ABC makes the contract explicit and supports DI in the interface layer.
    """

    @abstractmethod
    def build(self, result: SandboxValidationResult) -> BuiltReport:
        """
        Build a ``BuiltReport`` from *result*.

        Args:
            result: The output of the Sandbox Validation Engine.

        Returns:
            A fully assembled ``BuiltReport`` ready for formatting.
        """
