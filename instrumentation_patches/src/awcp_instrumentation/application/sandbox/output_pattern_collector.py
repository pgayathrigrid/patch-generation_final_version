"""
Concrete evidence collector: OutputPatternCollector.

Searches stdout and stderr for category-specific text patterns that indicate
a governance hook ran during execution.  This is the default evidence
collection strategy; it works with any Python agent because all standard
logging goes to stderr and print() goes to stdout.

Signal catalog
--------------
The default catalog maps each ``HookCategory`` to a list of case-insensitive
substring patterns.  The catalog is injectable so teams can extend or replace
it per governance policy without changing this class.

Limitation
~~~~~~~~~~
Pattern matching can produce false positives (a log message that contains the
word "task_started" does not guarantee the AWCP hook ran) and false negatives
(a hook that emits no visible output would not be detected here).  Observations
produced by this collector are therefore treated as *supporting evidence*, not
as the authoritative pass/fail signal — that comes from ``HookPresenceChecker``
(static analysis) and the subprocess exit code.

Future specialised collectors (``TraceCollector``, ``StructuredLogCollector``)
can provide higher-fidelity observations for the same hook categories.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from awcp_instrumentation.application.generator.models import PatchProposal
from awcp_instrumentation.application.sandbox.evidence_collector import EvidenceCollector
from awcp_instrumentation.application.sandbox.models import ExecutionRecord, RuntimeObservation
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# ---------------------------------------------------------------------------
# Default signal catalog
# ---------------------------------------------------------------------------

_DEFAULT_SIGNALS: Dict[HookCategory, List[str]] = {
    HookCategory.TASK_STARTED: [
        "task_started", "on_task_start", "awcp_hooks.task_started",
        "task started", "task_begin", "task_init",
    ],
    HookCategory.TASK_COMPLETED: [
        "task_completed", "on_task_complete", "awcp_hooks.task_completed",
        "task completed", "task_done", "task_finish",
    ],
    HookCategory.TASK_FAILED: [
        "task_failed", "on_task_fail", "awcp_hooks.task_failed",
        "task failed", "task_error", "task_exception",
    ],
    HookCategory.LLM_CALL: [
        "llm_call", "on_llm_call", "awcp_hooks.llm_call",
        "before_llm", "on_llm_start", "llm call",
    ],
    HookCategory.SYNTHESIZE: [
        "synthesize", "on_synthesize", "awcp_hooks.synthesize",
        "synthesis_hook", "on_synthesis", "synthesizing",
    ],
    HookCategory.TOOL_CALL: [
        "tool_call", "on_tool_call", "awcp_hooks.tool_call",
        "on_tool_start", "tool call", "tool_invoke",
    ],
    HookCategory.WEB_SEARCH: [
        "web_search", "on_web_search", "awcp_hooks.web_search",
        "search_hook", "on_search", "searching",
    ],
    HookCategory.TOKEN_USAGE: [
        "token_usage", "on_token_usage", "awcp_hooks.token_usage",
        "track_tokens", "token_tracker", "tokens used",
    ],
    HookCategory.BUDGET_WARN: [
        "budget_warn", "on_budget_warn", "awcp_hooks.budget_warn",
        "budget_warning", "budget warning", "budget threshold",
    ],
    HookCategory.BUDGET_EXHAUSTED: [
        "budget_exhausted", "on_budget_exhausted", "awcp_hooks.budget_exhausted",
        "budget exhausted", "budget exceeded", "budget_exceeded",
    ],
}


# ---------------------------------------------------------------------------
# OutputPatternCollector
# ---------------------------------------------------------------------------

class OutputPatternCollector(EvidenceCollector):
    """
    Scans stdout and stderr for governance hook signal patterns.

    Args:
        signal_catalog: Optional mapping of ``HookCategory`` → list of patterns.
                        Patterns are matched case-sensitively as substrings of
                        the combined output (stdout + "\\n" + stderr).
                        Defaults to ``_DEFAULT_SIGNALS``.
    """

    def __init__(
        self,
        signal_catalog: Optional[Dict[HookCategory, List[str]]] = None,
    ) -> None:
        self._catalog: Dict[HookCategory, List[str]] = (
            signal_catalog if signal_catalog is not None else _DEFAULT_SIGNALS
        )

    @property
    def collector_name(self) -> str:
        return "output_pattern"

    def collect(
        self,
        record: ExecutionRecord,
        applied_proposals: List[PatchProposal],
    ) -> List[RuntimeObservation]:
        """
        Return one ``RuntimeObservation`` per proposal.

        For each proposal, the combined stdout+stderr is searched for any
        pattern in the catalog entry for that hook's category.  The first
        matching excerpt is captured; all searched patterns are listed in
        ``RuntimeObservation.signal_patterns``.
        """
        observations: List[RuntimeObservation] = []
        combined = record.combined_output

        for proposal in applied_proposals:
            category = proposal.category
            hook_name = proposal.gap.hook.name
            patterns = self._catalog.get(category, [])

            stdout_excerpt, stderr_excerpt, observed = self._search(
                patterns=patterns,
                stdout=record.stdout,
                stderr=record.stderr,
                combined=combined,
            )

            observations.append(
                RuntimeObservation(
                    category=category,
                    hook_name=hook_name,
                    observed=observed,
                    stdout_excerpt=stdout_excerpt,
                    stderr_excerpt=stderr_excerpt,
                    signal_patterns=list(patterns),
                    collector_name=self.collector_name,
                )
            )

        return observations

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _search(
        patterns: List[str],
        stdout: str,
        stderr: str,
        combined: str,
    ) -> tuple[str, str, bool]:
        """
        Search *stdout* and *stderr* for any pattern in *patterns*.

        Returns:
            (stdout_excerpt, stderr_excerpt, observed)
            Excerpts are the line that first matched (empty when no match).
        """
        if not patterns:
            return "", "", False

        stdout_excerpt = ""
        stderr_excerpt = ""
        observed = False

        for pattern in patterns:
            if not stdout_excerpt:
                line = _first_matching_line(stdout, pattern)
                if line:
                    stdout_excerpt = line
                    observed = True

            if not stderr_excerpt:
                line = _first_matching_line(stderr, pattern)
                if line:
                    stderr_excerpt = line
                    observed = True

            if stdout_excerpt and stderr_excerpt:
                break

        return stdout_excerpt, stderr_excerpt, observed


def _first_matching_line(text: str, pattern: str) -> str:
    """Return the first line of *text* that contains *pattern*, or ''."""
    for line in text.splitlines():
        if pattern in line:
            return line.strip()
    return ""
