"""
Concrete formatter: MarkdownFormatter.

Renders a ``BuiltReport`` as GitHub-Flavoured Markdown.

Structure
---------
# Governance Validation Report — <agent_name>
## Summary
## Agent Information
## Execution Summary
## Hook Validation Results
## Missing / Failed Hooks      (only when failed_hooks > 0)
## Runtime Observations        (only when observations exist)
## Errors                      (always present; "None" when empty)
## Warnings                    (always present; "None" when empty)
## Recommendations             (only when recommendations exist)
## Evidence

Adding a new section (e.g. "Patch Diff") means extending this class only.
Adding a different format (HTML) means implementing a new ``ReportFormatter``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from awcp_instrumentation.application.reporter.interface import ReportFormatter
from awcp_instrumentation.application.reporter.models import (
    BuiltReport,
    HookRecommendation,
    HookResult,
    ObservationSummary,
    ReportError,
    ReportWarning,
)

_STATUS_ICON = {
    "passed": "✅",
    "failed": "❌",
    "skipped": "⏭️",
    "pending": "⏳",
}


class MarkdownFormatter(ReportFormatter):
    """
    Renders a ``BuiltReport`` as GitHub-Flavoured Markdown.

    Args:
        include_stdout_stderr: When True, stdout/stderr excerpts from hook
                               results are included in the hook table.
                               Default: False (keeps the table concise).
    """

    def __init__(self, include_stdout_stderr: bool = False) -> None:
        self._include_io = include_stdout_stderr

    @property
    def format_name(self) -> str:
        return "markdown"

    def format(self, report: BuiltReport) -> str:
        sections: List[str] = [
            self._header(report),
            self._section_summary(report),
            self._section_agent(report),
            self._section_execution(report),
            self._section_hook_results(report),
        ]

        if report.failed_hooks > 0:
            sections.append(self._section_missing_hooks(report))

        if report.has_observations:
            sections.append(self._section_observations(report))

        sections.append(self._section_errors(report))
        sections.append(self._section_warnings(report))

        if report.has_recommendations:
            sections.append(self._section_recommendations(report))

        sections.append(self._section_evidence(report))

        return "\n\n".join(s for s in sections if s) + "\n"

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    @staticmethod
    def _header(report: BuiltReport) -> str:
        icon = _STATUS_ICON.get(report.overall_status, "")
        return f"# {icon} Governance Validation Report — {report.agent.name}"

    @staticmethod
    def _section_summary(report: BuiltReport) -> str:
        ts = report.generated_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        lines = [
            "## Summary",
            "",
            f"**Status:** `{report.overall_status.upper()}`  ",
            f"**Generated:** {ts}  ",
            f"**Environment:** `{report.execution_summary.environment}`  ",
            "",
            f"> {report.summary}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _section_agent(report: BuiltReport) -> str:
        rows = [
            ("Name", f"`{report.agent.name}`"),
            ("Path", f"`{report.agent.path}`" if report.agent.path else "_unknown_"),
        ]
        return "## Agent Information\n\n" + _md_table(["Field", "Value"], rows)

    @staticmethod
    def _section_execution(report: BuiltReport) -> str:
        es = report.execution_summary
        duration = f"{es.duration_ms:.1f} ms" if es.duration_ms is not None else "_N/A_"
        exit_str = str(es.exit_code) if es.exit_code is not None else "_N/A_"
        rows = [
            ("Mode", f"`{es.mode}`"),
            ("Environment", f"`{es.environment}`"),
            ("Executed", "Yes" if es.executed else "No"),
            ("Duration", duration),
            ("Exit Code", exit_str),
            ("Timed Out", "Yes ⚠️" if es.timed_out else "No"),
            ("Syntax Valid", "Yes ✅" if es.syntax_valid else "No ❌"),
        ]
        return "## Execution Summary\n\n" + _md_table(["Field", "Value"], rows)

    def _section_hook_results(self, report: BuiltReport) -> str:
        if not report.hook_results:
            return "## Hook Validation Results\n\n_No hooks were validated._"

        headers = ["Category", "Hook Name", "Status", "Message"]
        rows = []
        for r in report.hook_results:
            icon = _STATUS_ICON.get(r.status, "")
            rows.append((
                r.category,
                f"`{r.hook_name}`",
                f"{icon} `{r.status.upper()}`",
                r.message,
            ))

        result = "## Hook Validation Results\n\n" + _md_table(headers, rows)

        if self._include_io:
            io_lines = ["", "### Hook Output Detail", ""]
            for r in report.hook_results:
                if r.stdout or r.stderr:
                    io_lines.append(f"**{r.category} — {r.hook_name}**")
                    if r.stdout:
                        io_lines += ["", "stdout:", "```", r.stdout[:500], "```"]
                    if r.stderr:
                        io_lines += ["", "stderr:", "```", r.stderr[:500], "```"]
                    io_lines.append("")
            result += "\n".join(io_lines)

        return result

    @staticmethod
    def _section_missing_hooks(report: BuiltReport) -> str:
        lines = ["## Missing / Failed Hooks", ""]
        lines.append(
            "The following governance hooks failed validation and remain "
            "unaddressed:\n"
        )
        for cat in report.missing_hooks:
            lines.append(f"- **`{cat}`**")
        lines.append("")
        lines.append(
            "_Review the Recommendations section for remediation guidance._"
        )
        return "\n".join(lines)

    @staticmethod
    def _section_observations(report: BuiltReport) -> str:
        headers = ["Category", "Hook Name", "Observed", "Collector", "Signal"]
        rows = []
        for obs in report.observations:
            observed_str = "Yes ✅" if obs.observed else "No"
            signal = obs.stdout_excerpt or obs.stderr_excerpt or "_none_"
            rows.append((
                obs.category,
                f"`{obs.hook_name}`",
                observed_str,
                f"`{obs.collector}`",
                signal[:80],
            ))
        return "## Runtime Observations\n\n" + _md_table(headers, rows)

    @staticmethod
    def _section_errors(report: BuiltReport) -> str:
        if not report.errors:
            return "## Errors\n\n_No errors._"

        lines = ["## Errors", ""]
        for err in report.errors:
            lines.append(f"### `{err.error_type}` — {err.category}")
            lines.append("")
            lines.append(f"{err.message}")
            if err.traceback:
                lines += ["", "```", err.traceback[:1000], "```"]
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _section_warnings(report: BuiltReport) -> str:
        if not report.warnings:
            return "## Warnings\n\n_No warnings._"

        lines = ["## Warnings", ""]
        for w in report.warnings:
            lines.append(f"- **{w.category}**: {w.message}")
        return "\n".join(lines)

    @staticmethod
    def _section_recommendations(report: BuiltReport) -> str:
        lines = ["## Recommendations", ""]
        for rec in report.recommendations:
            lines.append(f"### `{rec.category}` — `{rec.hook_name}`")
            lines.append("")
            lines.append(f"**Action:** {rec.action}  ")
            lines.append(f"**Rationale:** {rec.rationale}  ")
            lines.append(f"**Hint:** {rec.hint}  ")
            lines.append(
                f"**Priority:** {rec.priority} | **Severity:** `{rec.severity.upper()}`"
            )
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _section_evidence(report: BuiltReport) -> str:
        es = report.execution_summary
        lines = ["## Evidence", ""]

        if not es.executed:
            lines.append("_Code was not executed (syntax-only or import-check mode)._")
            return "\n".join(lines)

        if es.stdout_excerpt:
            lines += ["**stdout:**", "```", es.stdout_excerpt, "```", ""]
        else:
            lines.append("**stdout:** _empty_  ")
            lines.append("")

        if es.stderr_excerpt:
            lines += ["**stderr:**", "```", es.stderr_excerpt, "```", ""]
        else:
            lines.append("**stderr:** _empty_  ")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _md_table(headers: List[str], rows: List[tuple]) -> str:
    """Render a GFM pipe table."""
    header_row = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    data_rows = ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join([header_row, separator] + data_rows)
