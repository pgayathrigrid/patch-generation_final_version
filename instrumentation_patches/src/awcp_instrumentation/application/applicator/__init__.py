"""
Patch Apply Engine — transforms PatchProposals into patched AgentSource objects.

Public surface:
    PatchApplier       — abstract port (interface.py)
    SourcePatchApplier — concrete implementation (patch_applier.py)
    ApplyResult        — top-level result (models.py)
    PatchedSource      — patched source + audit record (models.py)
    ApplyStatus        — SUCCESS / PARTIAL / FAILED (models.py)
    ApplyWarning       — non-fatal issue (models.py)
    ApplyError         — fatal per-proposal failure (models.py)
"""
from awcp_instrumentation.application.applicator.interface import PatchApplier
from awcp_instrumentation.application.applicator.models import (
    ApplyError,
    ApplyResult,
    ApplyStatus,
    ApplyWarning,
    PatchedSource,
)
from awcp_instrumentation.application.applicator.patch_applier import SourcePatchApplier

__all__ = [
    "PatchApplier",
    "SourcePatchApplier",
    "ApplyResult",
    "PatchedSource",
    "ApplyStatus",
    "ApplyWarning",
    "ApplyError",
]
