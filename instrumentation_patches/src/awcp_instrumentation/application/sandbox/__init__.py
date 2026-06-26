"""
Sandbox Validation Engine.

Validates patched Python source in an isolated environment before the patch
is accepted by the pipeline.

Public surface
--------------
SandboxValidator          — abstract port (interface.py)
PythonSandboxValidator    — concrete orchestrator (python_sandbox_validator.py)
SandboxEnvironment        — abstract port for execution backends (sandbox_environment.py)
LocalPythonSandbox        — subprocess-based execution adapter (local_python_sandbox.py)
EvidenceCollector         — abstract port for evidence collection (evidence_collector.py)
OutputPatternCollector    — stdout/stderr pattern matching adapter (output_pattern_collector.py)
HookPresenceChecker       — static fragment presence detector (hook_presence.py)
SandboxValidationResult   — top-level output type (models.py)
ValidationEvidence        — raw execution artefacts (models.py)
RuntimeObservation        — per-hook evidence from a collector (models.py)
ValidationError           — fatal per-hook or engine error (models.py)
ValidationWarning         — non-fatal issue (models.py)
SandboxExecutionMode      — controls validation depth (models.py)
ExecutionRecord           — raw return type from SandboxEnvironment (models.py)
"""
from awcp_instrumentation.application.sandbox.evidence_collector import EvidenceCollector
from awcp_instrumentation.application.sandbox.hook_presence import HookPresenceChecker
from awcp_instrumentation.application.sandbox.interface import SandboxValidator
from awcp_instrumentation.application.sandbox.local_python_sandbox import LocalPythonSandbox
from awcp_instrumentation.application.sandbox.models import (
    ExecutionRecord,
    RuntimeObservation,
    SandboxExecutionMode,
    SandboxValidationResult,
    ValidationError,
    ValidationEvidence,
    ValidationWarning,
)
from awcp_instrumentation.application.sandbox.output_pattern_collector import (
    OutputPatternCollector,
)
from awcp_instrumentation.application.sandbox.python_sandbox_validator import (
    PythonSandboxValidator,
)
from awcp_instrumentation.application.sandbox.sandbox_environment import SandboxEnvironment

__all__ = [
    "SandboxValidator",
    "PythonSandboxValidator",
    "SandboxEnvironment",
    "LocalPythonSandbox",
    "EvidenceCollector",
    "OutputPatternCollector",
    "HookPresenceChecker",
    "SandboxValidationResult",
    "ValidationEvidence",
    "RuntimeObservation",
    "ValidationError",
    "ValidationWarning",
    "SandboxExecutionMode",
    "ExecutionRecord",
]
