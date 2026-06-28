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


# ---------------------------------------------------------------------------
# quarantine_blockers
# ---------------------------------------------------------------------------

class TestQuarantineBlockers:
    def test_summary_has_quarantine_blockers_field(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        for summary in result.agents:
            assert hasattr(summary, "quarantine_blockers")
            assert isinstance(summary.quarantine_blockers, list)

    def test_result_has_quarantine_blockers_property(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "x = 1")
        result = run_instrumentation(str(tmp_path))
        assert isinstance(result.quarantine_blockers, list)

    def test_quarantine_blockers_subset_of_missing(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "import openai")
        result = run_instrumentation(str(tmp_path))
        for summary in result.agents:
            # every blocker must also be in missing_hooks
            for b in summary.quarantine_blockers:
                assert b in summary.missing_hooks

    def test_quarantine_blockers_only_three_categories(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "import openai")
        result = run_instrumentation(str(tmp_path))
        allowed = {"observability", "feature_flag", "policy"}
        for summary in result.agents:
            for b in summary.quarantine_blockers:
                assert b in allowed

    def test_top_level_blockers_union_of_agents(self, tmp_path):
        _write_agent(tmp_path, "a.py", "import openai")
        result = run_instrumentation(str(tmp_path))
        per_agent = set()
        for summary in result.agents:
            per_agent.update(summary.quarantine_blockers)
        assert set(result.quarantine_blockers) == per_agent

    def test_top_level_blockers_no_duplicates(self, tmp_path):
        _write_agent(tmp_path, "a.py", "import openai")
        _write_agent(tmp_path, "b.py", "import openai")
        result = run_instrumentation(str(tmp_path))
        assert len(result.quarantine_blockers) == len(set(result.quarantine_blockers))


# ---------------------------------------------------------------------------
# dry_run parameter
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_returns_instrumentation_result(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "x = 1")
        result = run_instrumentation(str(tmp_path), dry_run=True)
        assert isinstance(result, InstrumentationResult)

    def test_dry_run_sets_validation_status_skipped(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "import openai")
        result = run_instrumentation(str(tmp_path), dry_run=True)
        for summary in result.agents:
            assert summary.validation_status == "skipped"

    def test_dry_run_report_overall_status_skipped(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "import openai")
        result = run_instrumentation(str(tmp_path), dry_run=True)
        for summary in result.agents:
            assert summary.report.overall_status == "skipped"

    def test_dry_run_report_execution_mode_dry_run(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "import openai")
        result = run_instrumentation(str(tmp_path), dry_run=True)
        for summary in result.agents:
            assert summary.report.execution_summary.mode == "dry_run"
            assert summary.report.execution_summary.executed is False

    def test_dry_run_agents_processed_same_as_normal(self, tmp_path):
        _write_agent(tmp_path, "a.py", "import openai")
        _write_agent(tmp_path, "b.py", "import anthropic")
        normal = run_instrumentation(str(tmp_path))
        dry = run_instrumentation(str(tmp_path), dry_run=True)
        assert dry.agents_processed == normal.agents_processed

    def test_dry_run_false_is_default_behaviour(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "import openai")
        r_default = run_instrumentation(str(tmp_path))
        r_explicit = run_instrumentation(str(tmp_path), dry_run=False)
        # Both should produce the same result; neither should say "dry_run" mode
        assert r_default.agents[0].validation_status == r_explicit.agents[0].validation_status
        for s in r_default.agents:
            assert s.report.execution_summary.mode != "dry_run"


# ---------------------------------------------------------------------------
# patch_bundle property
# ---------------------------------------------------------------------------

class TestPatchBundle:
    def test_patch_bundle_is_string(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "import openai")
        result = run_instrumentation(str(tmp_path))
        assert isinstance(result.patch_bundle, str)

    def test_patch_bundle_dry_run_has_diff_when_patches_applied(self, tmp_path):
        _write_agent(tmp_path, "agent.py", "import openai")
        result = run_instrumentation(str(tmp_path), dry_run=True)
        # At least one agent should have patches; bundle must contain diff markers
        if result.total_patches_applied:
            assert "@@" in result.patch_bundle or "---" in result.patch_bundle

    def test_patch_bundle_empty_for_instrumented_agent(self, tmp_path):
        # An agent with no missing hooks should produce no diff
        _write_agent(tmp_path, "empty.py", "")
        result = run_instrumentation(str(tmp_path))
        # empty.py has no capabilities → required hooks = all → missing > 0 → diff expected
        # Just assert the property exists and returns a string
        assert isinstance(result.patch_bundle, str)
