"""Tests for Patch Apply Engine models."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from awcp_instrumentation.application.applicator.models import (
    ApplyError,
    ApplyResult,
    ApplyStatus,
    ApplyWarning,
    PatchedSource,
)
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

ORIGINAL_SOURCE = "import os\n\ndef run():\n    pass\n"
PATCHED_SOURCE = "import os\nimport logging\n\ndef run():\n    logger.info('x')\n    pass\n"


def make_agent(source: str = ORIGINAL_SOURCE, name: str = "test_agent") -> AgentSource:
    return AgentSource.from_string(source, name)


def make_patched(
    original_source: str = ORIGINAL_SOURCE,
    patched_source: str = PATCHED_SOURCE,
    applied: list | None = None,
    warnings: list | None = None,
    errors: list | None = None,
) -> PatchedSource:
    return PatchedSource(
        original_agent=make_agent(original_source),
        patched_source=patched_source,
        applied_proposals=applied or [],
        warnings=warnings or [],
        errors=errors or [],
    )


# ---------------------------------------------------------------------------
# ApplyWarning
# ---------------------------------------------------------------------------

class TestApplyWarning:
    def test_is_frozen(self) -> None:
        w = ApplyWarning(category=HookCategory.TASK_STARTED, message="test")
        with pytest.raises((AttributeError, TypeError)):
            w.message = "other"  # type: ignore[misc]

    def test_fields(self) -> None:
        w = ApplyWarning(category=HookCategory.TASK_FAILED, message="fallback used")
        assert w.category == HookCategory.TASK_FAILED
        assert w.message == "fallback used"


# ---------------------------------------------------------------------------
# ApplyError
# ---------------------------------------------------------------------------

class TestApplyError:
    def test_is_frozen(self) -> None:
        e = ApplyError(category=HookCategory.LLM_CALL, message="fail")
        with pytest.raises((AttributeError, TypeError)):
            e.message = "other"  # type: ignore[misc]

    def test_original_exception_defaults_none(self) -> None:
        e = ApplyError(category=HookCategory.LLM_CALL, message="fail")
        assert e.original_exception is None

    def test_original_exception_stored(self) -> None:
        e = ApplyError(
            category=HookCategory.BUDGET_WARN,
            message="err",
            original_exception="ValueError: bad",
        )
        assert e.original_exception == "ValueError: bad"


# ---------------------------------------------------------------------------
# PatchedSource
# ---------------------------------------------------------------------------

class TestPatchedSource:
    def test_has_changes_true_when_different(self) -> None:
        ps = make_patched()
        assert ps.has_changes is True

    def test_has_changes_false_when_same(self) -> None:
        ps = make_patched(patched_source=ORIGINAL_SOURCE)
        assert ps.has_changes is False

    def test_applied_count(self) -> None:
        ps = make_patched(applied=[MagicMock(), MagicMock()])
        assert ps.applied_count == 2

    def test_error_count(self) -> None:
        err = ApplyError(category=HookCategory.TASK_FAILED, message="x")
        ps = make_patched(errors=[err])
        assert ps.error_count == 1

    def test_warning_count(self) -> None:
        w = ApplyWarning(category=HookCategory.TASK_STARTED, message="w")
        ps = make_patched(warnings=[w])
        assert ps.warning_count == 1

    def test_as_agent_source_preserves_name(self) -> None:
        ps = make_patched()
        result = ps.as_agent_source
        assert result.agent_name == "test_agent"

    def test_as_agent_source_uses_patched_code(self) -> None:
        ps = make_patched()
        assert ps.as_agent_source.source_code == PATCHED_SOURCE

    def test_diff_empty_when_no_changes(self) -> None:
        ps = make_patched(patched_source=ORIGINAL_SOURCE)
        assert ps.diff == ""

    def test_diff_non_empty_when_changed(self) -> None:
        ps = make_patched()
        assert "@@" in ps.diff

    def test_diff_includes_agent_name(self) -> None:
        ps = make_patched()
        assert "test_agent" in ps.diff

    def test_zero_counts_when_empty(self) -> None:
        ps = make_patched(applied=[], warnings=[], errors=[])
        assert ps.applied_count == 0
        assert ps.warning_count == 0
        assert ps.error_count == 0


# ---------------------------------------------------------------------------
# ApplyResult
# ---------------------------------------------------------------------------

class TestApplyResult:
    def _make_result(
        self,
        patched: PatchedSource | None = None,
        status: ApplyStatus = ApplyStatus.SUCCESS,
    ) -> ApplyResult:
        gen = MagicMock()
        return ApplyResult(
            generation_result=gen,
            patched_source=patched,
            status=status,
            generated_at=datetime.utcnow(),
        )

    def test_is_successful_true(self) -> None:
        result = self._make_result(status=ApplyStatus.SUCCESS)
        assert result.is_successful is True

    def test_is_successful_false_partial(self) -> None:
        result = self._make_result(status=ApplyStatus.PARTIAL)
        assert result.is_successful is False

    def test_is_successful_false_failed(self) -> None:
        result = self._make_result(status=ApplyStatus.FAILED)
        assert result.is_successful is False

    def test_has_warnings_true(self) -> None:
        w = ApplyWarning(category=HookCategory.TASK_STARTED, message="w")
        ps = make_patched(warnings=[w])
        result = self._make_result(patched=ps)
        assert result.has_warnings is True

    def test_has_warnings_false_when_no_patched(self) -> None:
        result = self._make_result(patched=None)
        assert result.has_warnings is False

    def test_has_errors_true(self) -> None:
        err = ApplyError(category=HookCategory.TASK_FAILED, message="x")
        ps = make_patched(errors=[err])
        result = self._make_result(patched=ps)
        assert result.has_errors is True

    def test_has_errors_false_when_no_patched(self) -> None:
        result = self._make_result(patched=None)
        assert result.has_errors is False

    def test_metadata_default_empty(self) -> None:
        result = self._make_result()
        assert result.metadata == {}

    def test_generated_at_type(self) -> None:
        result = self._make_result()
        assert isinstance(result.generated_at, datetime)
