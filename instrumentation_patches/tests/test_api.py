"""Integration-level tests for the public run_instrumentation() API."""
from __future__ import annotations

import tempfile
import textwrap
from pathlib import Path

import pytest

from awcp_instrumentation import run_instrumentation, InstrumentationResult, AgentInstrumentationSummary


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_agent(tmp_path: Path, filename: str, source: str) -> Path:
    p = tmp_path / filename
    p.write_text(textwrap.dedent(source))
    return p


# ---------------------------------------------------------------------------
# Basic contract
# ---------------------------------------------------------------------------

class TestRunInstrumentationContract:
    def test_returns_instrumentation_result(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        assert isinstance(result, InstrumentationResult)

    def test_invalid_path_raises(self):
        with pytest.raises(ValueError, match="does not exist"):
            run_instrumentation("/does/not/exist/xyz")

    def test_scanned_files_count(self, tmp_path):
        _write_agent(tmp_path, "a.py", "x = 1")
        _write_agent(tmp_path, "b.py", "y = 2")
        result = run_instrumentation(str(tmp_path))
        assert result.scanned_files == 2

    def test_repository_path_is_absolute(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        assert Path(result.repository_path).is_absolute()


# ---------------------------------------------------------------------------
# AgentInstrumentationSummary has capability fields
# ---------------------------------------------------------------------------

class TestSummaryCapabilityFields:
    def test_summary_has_capabilities_list(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        assert result.agents
        for summary in result.agents:
            assert hasattr(summary, "capabilities")
            assert isinstance(summary.capabilities, list)

    def test_summary_has_required_hooks_list(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        for summary in result.agents:
            assert hasattr(summary, "required_hooks")
            assert isinstance(summary.required_hooks, list)

    def test_plain_agent_detects_no_capabilities(self, tmp_path):
        _write_agent(tmp_path, "plain.py", "x = 1 + 2\nprint(x)")
        result = run_instrumentation(str(tmp_path))
        summary = result.agents[0]
        assert summary.capabilities == []

    def test_plain_agent_requires_all_hooks_as_fallback(self, tmp_path):
        _write_agent(tmp_path, "plain.py", "x = 42")
        result = run_instrumentation(str(tmp_path))
        summary = result.agents[0]
        # When no capability detected, all hooks are required (fallback covers all)
        from awcp_instrumentation.domain.enums.hook_category import HookCategory
        assert len(summary.required_hooks) == len(HookCategory)

    def test_llm_agent_detects_llm_capability(self, tmp_path):
        _write_agent(tmp_path, "llm_agent.py", "import openai\nresponse = openai.chat.completions.create()")
        result = run_instrumentation(str(tmp_path))
        summary = result.agents[0]
        assert "llm_agent" in summary.capabilities

    def test_llm_agent_does_not_require_tool_call_hook(self, tmp_path):
        _write_agent(tmp_path, "llm_agent.py", "import anthropic\nclient = anthropic.Anthropic()")
        result = run_instrumentation(str(tmp_path))
        summary = result.agents[0]
        assert "tool_call" not in summary.required_hooks

    def test_llm_agent_requires_llm_hooks(self, tmp_path):
        _write_agent(tmp_path, "llm_agent.py", "import openai")
        result = run_instrumentation(str(tmp_path))
        summary = result.agents[0]
        assert "llm_call" in summary.required_hooks
        assert "token_usage" in summary.required_hooks
        assert "budget_warn" in summary.required_hooks
        assert "budget_exhausted" in summary.required_hooks

    def test_missing_hooks_scoped_to_required(self, tmp_path):
        # TOOL_CALL should not appear in missing_hooks for a pure LLM agent
        _write_agent(tmp_path, "llm_agent.py", "import openai")
        result = run_instrumentation(str(tmp_path))
        summary = result.agents[0]
        assert "tool_call" not in summary.missing_hooks

    def test_task_hooks_always_required(self, tmp_path):
        _write_agent(tmp_path, "llm_agent.py", "import openai")
        result = run_instrumentation(str(tmp_path))
        summary = result.agents[0]
        assert "task_started" in summary.required_hooks
        assert "task_completed" in summary.required_hooks
        assert "task_failed" in summary.required_hooks


# ---------------------------------------------------------------------------
# Aggregate properties
# ---------------------------------------------------------------------------

class TestAggregateProperties:
    def test_total_missing_hooks(self, tmp_path):
        _write_agent(tmp_path, "a.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        assert isinstance(result.total_missing_hooks, int)

    def test_total_patches_applied(self, tmp_path):
        _write_agent(tmp_path, "a.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        assert isinstance(result.total_patches_applied, int)

    def test_total_warnings_is_int(self, tmp_path):
        _write_agent(tmp_path, "a.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        assert isinstance(result.total_warnings, int)

    def test_total_errors_is_int(self, tmp_path):
        _write_agent(tmp_path, "a.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        assert isinstance(result.total_errors, int)

    def test_repository_summary_is_string(self, tmp_path):
        _write_agent(tmp_path, "a.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        assert isinstance(result.repository_summary, str)
        assert len(result.repository_summary) > 0

    def test_repository_summary_empty_dir(self, tmp_path):
        result = run_instrumentation(str(tmp_path))
        assert "No agents found" in result.repository_summary

    def test_success_property_type(self, tmp_path):
        _write_agent(tmp_path, "a.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        assert isinstance(result.success, bool)


# ---------------------------------------------------------------------------
# AgentInstrumentationSummary warnings and errors fields
# ---------------------------------------------------------------------------

class TestSummaryWarningsAndErrors:
    def test_summary_has_warnings_list(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        for summary in result.agents:
            assert hasattr(summary, "warnings")
            assert isinstance(summary.warnings, list)

    def test_summary_has_errors_list(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        for summary in result.agents:
            assert hasattr(summary, "errors")
            assert isinstance(summary.errors, list)

    def test_summary_success_property(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        for summary in result.agents:
            assert isinstance(summary.success, bool)

    def test_summary_is_fully_instrumented_property(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        for summary in result.agents:
            assert isinstance(summary.is_fully_instrumented, bool)

    def test_warnings_are_strings(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "import openai")
        result = run_instrumentation(str(tmp_path))
        for summary in result.agents:
            assert all(isinstance(w, str) for w in summary.warnings)

    def test_errors_are_strings(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "import openai")
        result = run_instrumentation(str(tmp_path))
        for summary in result.agents:
            assert all(isinstance(e, str) for e in summary.errors)
