"""Tests for LocalPythonSandbox — subprocess-based SandboxEnvironment."""
from __future__ import annotations

import pytest

from awcp_instrumentation.application.sandbox.local_python_sandbox import LocalPythonSandbox
from awcp_instrumentation.application.sandbox.models import ExecutionRecord

SANDBOX = LocalPythonSandbox()


# ---------------------------------------------------------------------------
# environment_name
# ---------------------------------------------------------------------------

class TestEnvironmentName:
    def test_name_is_local_python(self) -> None:
        assert SANDBOX.environment_name == "local_python"


# ---------------------------------------------------------------------------
# Successful execution
# ---------------------------------------------------------------------------

class TestSuccessfulExecution:
    def test_returns_execution_record(self) -> None:
        result = SANDBOX.execute("x = 1", "test_agent", timeout_seconds=5.0)
        assert isinstance(result, ExecutionRecord)

    def test_exit_code_zero_on_success(self) -> None:
        result = SANDBOX.execute("x = 1 + 1", "test", timeout_seconds=5.0)
        assert result.exit_code == 0

    def test_succeeded_true(self) -> None:
        result = SANDBOX.execute("pass", "test", timeout_seconds=5.0)
        assert result.succeeded is True

    def test_captures_stdout(self) -> None:
        result = SANDBOX.execute("print('hello sandbox')", "test", timeout_seconds=5.0)
        assert "hello sandbox" in result.stdout

    def test_captures_stderr(self) -> None:
        result = SANDBOX.execute(
            "import sys; print('err msg', file=sys.stderr)",
            "test",
            timeout_seconds=5.0,
        )
        assert "err msg" in result.stderr

    def test_duration_ms_positive(self) -> None:
        result = SANDBOX.execute("pass", "test", timeout_seconds=5.0)
        assert result.duration_ms >= 0.0

    def test_not_timed_out(self) -> None:
        result = SANDBOX.execute("pass", "test", timeout_seconds=5.0)
        assert result.timed_out is False

    def test_empty_metadata(self) -> None:
        result = SANDBOX.execute("pass", "test", timeout_seconds=5.0)
        assert result.metadata == {}


# ---------------------------------------------------------------------------
# Runtime errors
# ---------------------------------------------------------------------------

class TestRuntimeErrors:
    def test_nonzero_exit_on_exception(self) -> None:
        result = SANDBOX.execute("raise ValueError('boom')", "test", timeout_seconds=5.0)
        assert result.exit_code != 0

    def test_traceback_in_stderr(self) -> None:
        result = SANDBOX.execute("raise ValueError('boom')", "test", timeout_seconds=5.0)
        assert "ValueError" in result.stderr

    def test_succeeded_false_on_exception(self) -> None:
        result = SANDBOX.execute("raise RuntimeError('x')", "test", timeout_seconds=5.0)
        assert result.succeeded is False

    def test_syntax_error_nonzero_exit(self) -> None:
        result = SANDBOX.execute("def broken(:\n    pass", "test", timeout_seconds=5.0)
        assert result.exit_code != 0

    def test_import_error_nonzero_exit(self) -> None:
        result = SANDBOX.execute(
            "import nonexistent_module_xyz", "test", timeout_seconds=5.0
        )
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------

class TestTimeout:
    def test_timeout_sets_timed_out_flag(self) -> None:
        result = SANDBOX.execute(
            "import time; time.sleep(30)", "test", timeout_seconds=0.5
        )
        assert result.timed_out is True

    def test_timeout_exit_code_nonzero(self) -> None:
        result = SANDBOX.execute(
            "import time; time.sleep(30)", "test", timeout_seconds=0.5
        )
        assert result.exit_code != 0

    def test_timeout_succeeded_false(self) -> None:
        result = SANDBOX.execute(
            "import time; time.sleep(30)", "test", timeout_seconds=0.5
        )
        assert result.succeeded is False


# ---------------------------------------------------------------------------
# Agent name sanitisation
# ---------------------------------------------------------------------------

class TestAgentName:
    def test_special_chars_in_agent_name(self) -> None:
        # Should not raise — special chars are sanitised in the temp file name
        result = SANDBOX.execute("pass", "agent with spaces & symbols!", timeout_seconds=5.0)
        assert result.exit_code == 0

    def test_empty_agent_name(self) -> None:
        result = SANDBOX.execute("pass", "", timeout_seconds=5.0)
        assert result.exit_code == 0
