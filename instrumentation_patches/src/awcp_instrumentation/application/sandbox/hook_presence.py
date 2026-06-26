"""
Static hook presence checker.

Determines whether a ``PatchChange`` code fragment was successfully incorporated
into the patched source without executing any code.

This is the primary pass/fail signal for each governance hook.  It runs before
(and independently of) subprocess execution, so it is always available even
when ``SandboxExecutionMode.SYNTAX_ONLY`` is selected.

Strategy
--------
Two checks are attempted in order; a fragment is considered present when either
passes:

1. **Exact substring match** — the ``code_fragment`` string appears verbatim
   in the patched source.  Handles most single-line fragments.

2. **Normalised match** — whitespace in both the fragment and the source is
   collapsed to single spaces and leading/trailing whitespace is stripped.
   Handles minor indentation differences introduced by ``SourceEditor``.

``HookPresenceChecker`` has no external dependencies and is always injected as
a concrete class (no abstract interface needed — it is pure text analysis with
no I/O and no plausible alternative implementation).
"""
from __future__ import annotations

import re
from typing import Dict, List, Tuple

from awcp_instrumentation.application.generator.models import PatchChange, PatchProposal


class HookPresenceChecker:
    """
    Stateless utility that checks whether patch fragments appear in source.

    All methods are pure: they accept source as a string and return results
    without any side effects.
    """

    def is_present(self, source: str, change: PatchChange) -> bool:
        """
        Return True when *change.code_fragment* can be found in *source*.

        Uses exact match first, then normalised match.
        """
        fragment = change.code_fragment
        if not fragment or not source:
            return False

        # Strategy 1: exact substring
        if fragment in source:
            return True

        # Strategy 2: normalised (collapse whitespace)
        if self._normalise(fragment) in self._normalise(source):
            return True

        return False

    def check_proposal(
        self, source: str, proposal: PatchProposal
    ) -> Dict[PatchChange, bool]:
        """
        Check every change in *proposal* and return a per-change presence map.

        Args:
            source:   The patched source code.
            proposal: The proposal whose changes will be checked.

        Returns:
            ``{change: True/False}`` for every change in ``proposal.changes``.
        """
        return {change: self.is_present(source, change) for change in proposal.changes}

    def all_present(self, source: str, proposal: PatchProposal) -> bool:
        """Return True when every change in *proposal* is present in *source*."""
        if not proposal.changes:
            return True
        return all(self.check_proposal(source, proposal).values())

    def missing_changes(
        self, source: str, proposals: List[PatchProposal]
    ) -> List[Tuple[PatchProposal, List[PatchChange]]]:
        """
        For each proposal, return a (proposal, missing_changes) pair.

        ``PatchProposal`` is not hashable (non-frozen dataclass), so results
        are returned as an ordered list of tuples rather than a dict.
        The inner list is empty for proposals where all changes are present.
        """
        result: List[Tuple[PatchProposal, List[PatchChange]]] = []
        for proposal in proposals:
            absent = [
                change
                for change, present in self.check_proposal(source, proposal).items()
                if not present
            ]
            result.append((proposal, absent))
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(text: str) -> str:
        """Collapse all whitespace runs to a single space and strip ends."""
        return re.sub(r"\s+", " ", text).strip()
