"""
Abstract port: SandboxEnvironment.

Defines the contract that any sandbox backend must fulfil.  The
``PythonSandboxValidator`` depends only on this interface, never on a
concrete implementation.

Concrete adapters
-----------------
LocalPythonSandbox  (local_python_sandbox.py)
    Runs the patched source in a child subprocess on the local machine.
    Suitable for local development and standard CI environments.

[future] CodeActSandbox
    Submits the patched source to a remote CodeAct service and retrieves
    execution artefacts over an API.  The ``ExecutionRecord.metadata`` field
    is the extension point for CodeAct-specific data (trace IDs, spans, etc.).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from awcp_instrumentation.application.sandbox.models import ExecutionRecord


class SandboxEnvironment(ABC):
    """
    Port: executes Python source code in an isolated environment.

    Implementors must be stateless with respect to a single ``execute`` call:
    each call is independent and must not share state with previous calls.
    """

    @abstractmethod
    def execute(
        self,
        source: str,
        agent_name: str,
        timeout_seconds: float,
    ) -> ExecutionRecord:
        """
        Execute *source* and return the raw artefacts.

        Args:
            source:          The Python source code to run.
            agent_name:      Used for temp-file naming and log messages.
            timeout_seconds: Maximum wall-clock time before the execution is
                             killed and ``ExecutionRecord.timed_out`` is set.

        Returns:
            An ``ExecutionRecord`` describing what happened.  Must never raise;
            all errors are encoded in the returned record (non-zero exit code,
            ``timed_out=True``, or stderr content).
        """

    @property
    @abstractmethod
    def environment_name(self) -> str:
        """
        Short identifier for this environment (e.g. ``"local_python"``).

        Stored in ``ValidationEvidence.environment_name`` so every validation
        record is traceable to the backend that produced it.
        """
