"""
Concrete Patch Apply Engine implementation.

Applies ``PatchProposal`` objects produced by the LLM Patch Generator to
Python source code using text-based line insertion.

Apply order
~~~~~~~~~~~
Proposals are applied sequentially in priority order (CRITICAL first,
matching the gap ordering from ``GovernanceGapReport.gaps_ordered_by_priority``).
After each successful apply the working source is updated so subsequent
proposals see the already-modified file.  Line numbers shift as code is
inserted, but each proposal's ``LocationResolver`` call operates on the
current (already-patched) source, so positions remain accurate.

Import injection
~~~~~~~~~~~~~~~~
After all ``PatchChange`` insertions, import additions from all successful
proposals are collected, deduplicated, and injected in a single pass using
``ImportManager``.  This avoids re-scanning the source after each proposal.

Error isolation
~~~~~~~~~~~~~~~
If one proposal fails (``LocationResolutionError``, unexpected exception)
it is recorded as an ``ApplyError`` and the next proposal is attempted with
the source left in its pre-error state.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Tuple

from awcp_instrumentation.application.applicator.import_manager import ImportManager
from awcp_instrumentation.application.applicator.interface import PatchApplier
from awcp_instrumentation.application.applicator.location_resolver import (
    LocationResolutionError,
    LocationResolver,
)
from awcp_instrumentation.application.applicator.models import (
    ApplyError,
    ApplyResult,
    ApplyStatus,
    ApplyWarning,
    PatchedSource,
)
from awcp_instrumentation.application.applicator.source_editor import SourceEditor
from awcp_instrumentation.application.generator.models import (
    PatchGenerationResult,
    PatchProposal,
    ProposalStatus,
)
from awcp_instrumentation.domain.entities.agent_source import AgentSource


class SourcePatchApplier(PatchApplier):
    """
    Text-based patch applier using ``LocationResolver`` and ``SourceEditor``.

    Args:
        location_resolver: Resolves ``InsertionLocation`` to concrete line/indent.
        source_editor:     Performs line-level text insertions.
        import_manager:    Deduplicates and injects import statements.
    """

    def __init__(
        self,
        location_resolver: LocationResolver | None = None,
        source_editor: SourceEditor | None = None,
        import_manager: ImportManager | None = None,
    ) -> None:
        self._resolver = location_resolver or LocationResolver()
        self._editor = source_editor or SourceEditor()
        self._imports = import_manager or ImportManager()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply(
        self,
        agent: AgentSource,
        generation_result: PatchGenerationResult,
    ) -> ApplyResult:
        """
        Apply all successful proposals to *agent* and return the result.
        """
        successful_proposals = generation_result.successful_proposals
        if not successful_proposals:
            patched = PatchedSource(
                original_agent=agent,
                patched_source=agent.source_code,
                applied_proposals=[],
                warnings=[],
                errors=[
                    ApplyError(
                        category=p.category,
                        message=f"Proposal has status {p.status.value}; skipped.",
                    )
                    for p in generation_result.proposals
                    if p.status != ProposalStatus.SUCCESS
                ],
            )
            return ApplyResult(
                generation_result=generation_result,
                patched_source=patched,
                status=ApplyStatus.FAILED if generation_result.proposals else ApplyStatus.SUCCESS,
                generated_at=datetime.utcnow(),
            )

        working_source = agent.source_code
        applied: List[PatchProposal] = []
        warnings: List[ApplyWarning] = []
        errors: List[ApplyError] = []
        pending_imports: List[str] = []

        for proposal in successful_proposals:
            source_before = working_source
            proposal_ok = True

            for change in proposal.changes:
                try:
                    resolved = self._resolver.resolve(
                        location=change.location,
                        source=working_source,
                        target_function=change.target_function,
                    )
                except LocationResolutionError as exc:
                    errors.append(
                        ApplyError(
                            category=proposal.category,
                            message=(
                                f"Could not resolve location {change.location.value!r} "
                                f"for {proposal.category.value}: {exc}"
                            ),
                            original_exception=str(exc),
                        )
                    )
                    proposal_ok = False
                    break
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        ApplyError(
                            category=proposal.category,
                            message=f"Unexpected error resolving location: {exc}",
                            original_exception=str(exc),
                        )
                    )
                    proposal_ok = False
                    break

                if resolved.warning:
                    warnings.append(
                        ApplyWarning(
                            category=proposal.category,
                            message=resolved.warning,
                        )
                    )

                try:
                    working_source = self._editor.insert_before_line(
                        source=working_source,
                        line_number=resolved.line_number,
                        fragment=change.code_fragment,
                        indent=resolved.indent,
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(
                        ApplyError(
                            category=proposal.category,
                            message=f"Source edit failed: {exc}",
                            original_exception=str(exc),
                        )
                    )
                    working_source = source_before
                    proposal_ok = False
                    break

            if proposal_ok:
                applied.append(proposal)
                pending_imports.extend(proposal.import_additions)
            else:
                working_source = source_before

        # Inject all imports in a single deduplication pass
        if pending_imports:
            new_imports = self._imports.filter_new_imports(working_source, pending_imports)
            if new_imports:
                working_source = self._imports.inject_imports(working_source, new_imports)

        patched = PatchedSource(
            original_agent=agent,
            patched_source=working_source,
            applied_proposals=applied,
            warnings=warnings,
            errors=errors,
        )

        status = self._compute_status(patched)

        return ApplyResult(
            generation_result=generation_result,
            patched_source=patched,
            status=status,
            generated_at=datetime.utcnow(),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_status(patched: PatchedSource) -> ApplyStatus:
        if patched.error_count == 0:
            return ApplyStatus.SUCCESS
        if patched.applied_count > 0:
            return ApplyStatus.PARTIAL
        return ApplyStatus.FAILED
