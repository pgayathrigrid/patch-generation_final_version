"""
Concrete adapter: LocalPythonSandbox.

Runs patched Python source in a child subprocess on the local machine.
Each call is isolated: the source is written to a fresh temp file, executed
with ``subprocess.run``, and the temp file is removed regardless of outcome.

Suitable for local development and standard CI environments that permit
subprocess spawning.

Future environments (e.g. ``CodeActSandbox``) implement ``SandboxEnvironment``
without changing this file or the ``PythonSandboxValidator``.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import time
from pathlib import Path

from awcp_instrumentation.application.sandbox.models import ExecutionRecord
from awcp_instrumentation.application.sandbox.sandbox_environment import SandboxEnvironment

# Scratchpad directory for temp files; falls back to the system temp dir.
_SCRATCHPAD = Path(
    "/private/tmp/claude-501/-Users-pgayathri-instrumentation-patches"
    "/586a193d-8b08-4ceb-b8aa-04db54a74268/scratchpad"
)


class LocalPythonSandbox(SandboxEnvironment):
    """
    Runs Python source in an isolated child subprocess.

    The same Python interpreter that is running this process is used so that
    the sandbox shares the same package installation.  The patched agent code
    is written to a temporary ``.py`` file inside the scratchpad directory
    (or the system temp directory if the scratchpad is unavailable) and
    deleted immediately after execution.

    The child process has no access to the parent's in-memory state; it is
    a fresh interpreter invocation.

    Args:
        extra_env: Optional mapping of extra environment variables to pass to
                   the child process (merged on top of the current environment).
                   Useful for injecting ``PYTHONPATH`` overrides in tests.
    """

    def __init__(self, extra_env: dict[str, str] | None = None) -> None:
        self._extra_env = extra_env or {}

    # ------------------------------------------------------------------
    # SandboxEnvironment interface
    # ------------------------------------------------------------------

    @property
    def environment_name(self) -> str:
        return "local_python"

    def execute(
        self,
        source: str,
        agent_name: str,
        timeout_seconds: float,
    ) -> ExecutionRecord:
        """
        Write *source* to a temp file and run it with the current interpreter.

        The temp file is always deleted, even on exception or timeout.
        """
        tmp_path = self._write_temp_file(source, agent_name)
        try:
            return self._run(tmp_path, timeout_seconds)
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _write_temp_file(self, source: str, agent_name: str) -> Path:
        """Write *source* to a temporary ``.py`` file and return its path."""
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in agent_name)
        tmp_dir = _SCRATCHPAD if _SCRATCHPAD.exists() else Path(tempfile.gettempdir())
        fd, path_str = tempfile.mkstemp(
            prefix=f"sandbox_{safe_name}_",
            suffix=".py",
            dir=str(tmp_dir),
        )
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                fh.write(source)
        except Exception:
            Path(path_str).unlink(missing_ok=True)
            raise
        return Path(path_str)

    def _run(self, path: Path, timeout_seconds: float) -> ExecutionRecord:
        """
        Execute *path* with the current Python interpreter.

        Captures stdout and stderr separately.  Returns an ``ExecutionRecord``
        with ``timed_out=True`` when the process is killed by the timeout.
        """
        env = self._build_env()
        start = time.monotonic()
        timed_out = False
        try:
            proc = subprocess.run(
                [sys.executable, str(path)],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            exit_code = proc.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = (exc.stdout or b"").decode("utf-8", errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = (exc.stderr or b"").decode("utf-8", errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            exit_code = -1
        duration_ms = (time.monotonic() - start) * 1000.0

        return ExecutionRecord(
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            duration_ms=duration_ms,
            timed_out=timed_out,
        )

    def _build_env(self) -> dict[str, str]:
        """Merge the current environment with any extra variables."""
        import os
        env = dict(os.environ)
        env.update(self._extra_env)
        return env
