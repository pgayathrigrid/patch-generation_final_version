"""
Abstract port: SandboxValidator.

The single entry point into the Sandbox Validation Engine.  Downstream stages
(Validation Report module, AWCP integration layer) depend only on this
interface, never on the concrete ``PythonSandboxValidator``.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from awcp_instrumentation.application.applicator.models import PatchedSource
from awcp_instrumentation.application.sandbox.models import SandboxValidationResult


class SandboxValidator(ABC):
    """
    Port: validates a ``PatchedSource`` in an isolated environment.

    Must NOT:
    - Generate patches or call any LLM.
    - Modify source code.
    - Scan repositories.
    - Detect governance gaps.
    - Apply patches.
    """

    @abstractmethod
    def validate(self, patched: PatchedSource) -> SandboxValidationResult:
        """
        Validate *patched* and return a structured result.

        Args:
            patched: The output of the Patch Apply Engine.

        Returns:
            A ``SandboxValidationResult`` containing the domain-layer
            ``ValidationReport`` and all raw execution evidence.
        """
