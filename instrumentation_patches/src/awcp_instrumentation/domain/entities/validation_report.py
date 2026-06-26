from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory
from awcp_instrumentation.domain.enums.validation_status import ValidationStatus


@dataclass
class HookValidationResult:
    """
    Outcome of validating a single governance hook inside the sandbox.

    Attributes:
        hook:          The hook under test.
        status:        Whether validation passed, failed, or was skipped.
        message:       Human-readable outcome detail.
        stdout:        Captured stdout from the sandbox run (if any).
        stderr:        Captured stderr from the sandbox run (if any).
    """

    hook: GovernanceHook
    status: ValidationStatus
    message: str = field(default="")
    stdout: str = field(default="")
    stderr: str = field(default="")


@dataclass
class ValidationReport:
    """
    The final output returned by the Patch Validation stage.

    Attributes:
        agent_name:       Name of the agent that was validated.
        overall_status:   Aggregate pass/fail across all hook validations.
        hook_results:     Per-hook validation outcomes.
        sandbox_log:      Full sandbox execution log.
        generated_at:     UTC timestamp of report creation.
        duration_seconds: How long the sandbox run took.
        metadata:         Arbitrary key/value pairs for downstream consumers.
    """

    agent_name: str
    overall_status: ValidationStatus
    hook_results: List[HookValidationResult] = field(default_factory=list)
    sandbox_log: str = field(default="")
    generated_at: datetime = field(default_factory=datetime.utcnow)
    duration_seconds: float = field(default=0.0)
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def passed(self) -> List[HookValidationResult]:
        return [r for r in self.hook_results if r.status == ValidationStatus.PASSED]

    @property
    def failed(self) -> List[HookValidationResult]:
        return [r for r in self.hook_results if r.status == ValidationStatus.FAILED]

    @property
    def skipped(self) -> List[HookValidationResult]:
        return [r for r in self.hook_results if r.status == ValidationStatus.SKIPPED]

    @property
    def summary(self) -> str:
        total = len(self.hook_results)
        return (
            f"Agent '{self.agent_name}': {self.overall_status.value.upper()} "
            f"({len(self.passed)}/{total} hooks passed)"
        )

    def hooks_by_category(self) -> Dict[HookCategory, List[HookValidationResult]]:
        result: Dict[HookCategory, List[HookValidationResult]] = {}
        for r in self.hook_results:
            result.setdefault(r.hook.category, []).append(r)
        return result
