from __future__ import annotations
"""Tests for LlmPatchGenerator and MockLlmProvider."""

import json
from typing import List

import pytest

from awcp_instrumentation.application.gap_reporter.models import (
    GovernanceGap,
    GovernanceGapReport,
    GovernanceRecommendation,
    GovernanceRisk,
    RiskSeverity,
)
from awcp_instrumentation.application.generator import (
    LlmPatchGenerator,
    LlmProviderError,
    MockLlmProvider,
    PatchGenerationResult,
    PatchGenerator,
    ProposalStatus,
)
from awcp_instrumentation.domain.entities.agent_source import AgentSource
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook
from awcp_instrumentation.domain.enums.hook_category import HookCategory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_hook(category: HookCategory) -> GovernanceHook:
    return GovernanceHook(category=category, name=f"{category.value}_hook", description="test")


def make_gap(category: HookCategory = HookCategory.TASK_STARTED) -> GovernanceGap:
    return GovernanceGap(
        hook=make_hook(category),
        risk=GovernanceRisk(severity=RiskSeverity.HIGH, description="risk", impact="impact"),
        recommendation=GovernanceRecommendation(
            action="add hook", rationale="required",
            instrumentation_hint="insert call at entry", priority=1,
        ),
    )


def make_agent(source: str = "def run():\n    pass") -> AgentSource:
    return AgentSource.from_string(source, name="test_agent")


def make_report(
    missing_categories: List[HookCategory] | None = None,
) -> GovernanceGapReport:
    categories = missing_categories or [HookCategory.TASK_STARTED, HookCategory.TASK_FAILED]
    gaps = [make_gap(c) for c in categories]
    return GovernanceGapReport(
        agent=make_agent(),
        present_hooks=[],
        gaps=gaps,
        overall_risk_level=RiskSeverity.HIGH,
        summary="test report",
    )


def valid_response_json() -> str:
    return json.dumps({
        "import_additions": ["import logging"],
        "changes": [{
            "code_fragment": "logging.info('action')",
            "location": "before_function_body",
            "target_function": "run",
            "explanation": "log at entry"
        }],
        "explanation": "Added logging hook",
        "confidence": 0.9,
    })


# ---------------------------------------------------------------------------
# MockLlmProvider
# ---------------------------------------------------------------------------

class TestMockLlmProvider:
    def test_is_llm_provider(self) -> None:
        from awcp_instrumentation.application.generator.llm_interface import LlmProvider
        assert isinstance(MockLlmProvider(), LlmProvider)

    def test_returns_response(self) -> None:
        from awcp_instrumentation.application.generator.llm_interface import LlmRequest
        request = LlmRequest(prompt="test", system_prompt="sys")
        response = MockLlmProvider().complete(request)
        assert response.content

    def test_custom_response_content(self) -> None:
        from awcp_instrumentation.application.generator.llm_interface import LlmRequest
        mock = MockLlmProvider(response_content=valid_response_json())
        request = LlmRequest(prompt="test", system_prompt="sys")
        response = mock.complete(request)
        assert response.content == valid_response_json()

    def test_call_count_increments(self) -> None:
        from awcp_instrumentation.application.generator.llm_interface import LlmRequest
        mock = MockLlmProvider()
        request = LlmRequest(prompt="test", system_prompt="sys")
        mock.complete(request)
        mock.complete(request)
        assert mock.call_count == 2

    def test_last_request_recorded(self) -> None:
        from awcp_instrumentation.application.generator.llm_interface import LlmRequest
        mock = MockLlmProvider()
        request = LlmRequest(prompt="hello world", system_prompt="sys")
        mock.complete(request)
        assert mock.last_request is not None
        assert mock.last_request.prompt == "hello world"

    def test_raise_error_on_complete(self) -> None:
        from awcp_instrumentation.application.generator.llm_interface import LlmRequest
        mock = MockLlmProvider(raise_error=LlmProviderError("API timeout"))
        with pytest.raises(LlmProviderError):
            mock.complete(LlmRequest(prompt="test", system_prompt="sys"))

    def test_default_model_name(self) -> None:
        assert MockLlmProvider().default_model == "mock-model-1.0"

    def test_custom_model_name(self) -> None:
        mock = MockLlmProvider(model_name="my-test-model")
        assert mock.default_model == "my-test-model"

    def test_provider_name(self) -> None:
        assert MockLlmProvider().provider_name == "MockLlmProvider"

    def test_model_override_in_request(self) -> None:
        from awcp_instrumentation.application.generator.llm_interface import LlmRequest
        mock = MockLlmProvider()
        request = LlmRequest(prompt="test", system_prompt="sys", model="override-model")
        response = mock.complete(request)
        assert response.model == "override-model"

    def test_simulated_token_counts(self) -> None:
        from awcp_instrumentation.application.generator.llm_interface import LlmRequest
        mock = MockLlmProvider(prompt_tokens=200, completion_tokens=100)
        response = mock.complete(LlmRequest(prompt="test", system_prompt="sys"))
        assert response.prompt_tokens == 200
        assert response.completion_tokens == 100

    def test_default_response_is_valid_json(self) -> None:
        from awcp_instrumentation.application.generator.llm_interface import LlmRequest
        mock = MockLlmProvider()
        response = mock.complete(LlmRequest(prompt="observability gap", system_prompt="sys"))
        data = json.loads(response.content)
        assert "changes" in data
        assert "import_additions" in data


# ---------------------------------------------------------------------------
# Interface contract
# ---------------------------------------------------------------------------

class TestPatchGeneratorInterface:
    def test_is_patch_generator(self) -> None:
        assert isinstance(LlmPatchGenerator(MockLlmProvider()), PatchGenerator)

    def test_generate_returns_result(self) -> None:
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        result = generator.generate(make_report())
        assert isinstance(result, PatchGenerationResult)


# ---------------------------------------------------------------------------
# generate() — full report
# ---------------------------------------------------------------------------

class TestGenerateFullReport:
    def test_one_proposal_per_gap(self) -> None:
        report = make_report([HookCategory.TASK_STARTED, HookCategory.TASK_FAILED])
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        result = generator.generate(report)
        assert len(result.proposals) == 2

    def test_empty_gaps_produces_empty_proposals(self) -> None:
        report = GovernanceGapReport(
            agent=make_agent(), present_hooks=[], gaps=[],
            overall_risk_level=RiskSeverity.NONE, summary="all good"
        )
        generator = LlmPatchGenerator(MockLlmProvider())
        result = generator.generate(report)
        assert result.proposals == []

    def test_result_links_back_to_report(self) -> None:
        report = make_report()
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        result = generator.generate(report)
        assert result.report is report

    def test_successful_proposals_have_success_status(self) -> None:
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        result = generator.generate(make_report())
        assert all(p.status == ProposalStatus.SUCCESS for p in result.proposals)

    def test_proposals_contain_changes(self) -> None:
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        result = generator.generate(make_report())
        assert all(p.has_changes for p in result.proposals)

    def test_is_complete_when_all_gaps_processed(self) -> None:
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        result = generator.generate(make_report([HookCategory.TASK_STARTED]))
        assert result.is_complete is True

    def test_metadata_includes_provider(self) -> None:
        generator = LlmPatchGenerator(MockLlmProvider())
        result = generator.generate(make_report())
        assert result.metadata.get("provider") == "MockLlmProvider"

    def test_total_tokens_summed(self) -> None:
        mock = MockLlmProvider(
            response_content=valid_response_json(),
            prompt_tokens=100, completion_tokens=50
        )
        result = LlmPatchGenerator(mock).generate(make_report())
        assert result.total_tokens == 150 * len(result.proposals)


# ---------------------------------------------------------------------------
# generate_for_gap()
# ---------------------------------------------------------------------------

class TestGenerateForGap:
    def test_returns_proposal(self) -> None:
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        proposal = generator.generate_for_gap(make_gap(), make_agent())
        assert proposal is not None

    def test_proposal_gap_matches_input(self) -> None:
        gap = make_gap(HookCategory.TOKEN_USAGE)
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        proposal = generator.generate_for_gap(gap, make_agent())
        assert proposal.gap is gap

    def test_proposal_has_correct_category(self) -> None:
        gap = make_gap(HookCategory.LLM_CALL)
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        proposal = generator.generate_for_gap(gap, make_agent())
        assert proposal.category == HookCategory.LLM_CALL

    def test_import_additions_preserved(self) -> None:
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        proposal = generator.generate_for_gap(make_gap(), make_agent())
        assert "import logging" in proposal.import_additions

    def test_confidence_within_range(self) -> None:
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        proposal = generator.generate_for_gap(make_gap(), make_agent())
        assert 0.0 <= proposal.confidence <= 1.0

    def test_raw_llm_response_stored(self) -> None:
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        proposal = generator.generate_for_gap(make_gap(), make_agent())
        assert proposal.raw_llm_response == valid_response_json()

    def test_metadata_model_set(self) -> None:
        generator = LlmPatchGenerator(
            MockLlmProvider(response_content=valid_response_json(), model_name="test-model")
        )
        proposal = generator.generate_for_gap(make_gap(), make_agent())
        assert proposal.metadata.model == "test-model"

    def test_metadata_provider_name_set(self) -> None:
        generator = LlmPatchGenerator(MockLlmProvider(response_content=valid_response_json()))
        proposal = generator.generate_for_gap(make_gap(), make_agent())
        assert proposal.metadata.provider_name == "MockLlmProvider"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_llm_provider_error_produces_failed_proposal(self) -> None:
        mock = MockLlmProvider(raise_error=LlmProviderError("timeout"))
        generator = LlmPatchGenerator(mock)
        proposal = generator.generate_for_gap(make_gap(), make_agent())
        assert proposal.status == ProposalStatus.FAILED

    def test_failed_proposal_has_error_message(self) -> None:
        mock = MockLlmProvider(raise_error=LlmProviderError("API key invalid"))
        generator = LlmPatchGenerator(mock)
        proposal = generator.generate_for_gap(make_gap(), make_agent())
        assert "API key invalid" in (proposal.error or "")

    def test_malformed_json_produces_failed_proposal(self) -> None:
        mock = MockLlmProvider(response_content="not json at all")
        generator = LlmPatchGenerator(mock)
        proposal = generator.generate_for_gap(make_gap(), make_agent())
        assert proposal.status == ProposalStatus.FAILED

    def test_one_failed_gap_does_not_abort_others(self) -> None:
        call_log = []
        # First call raises, second call succeeds
        responses = [LlmProviderError("fail"), None]

        class SelectiveMock(MockLlmProvider):
            def complete(self, request):
                call_log.append(request)
                if len(call_log) == 1:
                    raise LlmProviderError("fail on first call")
                return super().complete(request)

        mock = SelectiveMock(response_content=valid_response_json())
        generator = LlmPatchGenerator(mock)
        report = make_report([HookCategory.TASK_STARTED, HookCategory.TASK_FAILED])
        result = generator.generate(report)

        assert len(result.proposals) == 2
        assert result.proposals[0].status == ProposalStatus.FAILED
        assert result.proposals[1].status == ProposalStatus.SUCCESS

    def test_failed_proposal_has_no_changes(self) -> None:
        mock = MockLlmProvider(raise_error=LlmProviderError("error"))
        generator = LlmPatchGenerator(mock)
        proposal = generator.generate_for_gap(make_gap(), make_agent())
        assert proposal.changes == []
        assert proposal.import_additions == []

    def test_generate_never_raises_on_provider_error(self) -> None:
        mock = MockLlmProvider(raise_error=LlmProviderError("all failing"))
        generator = LlmPatchGenerator(mock)
        report = make_report()
        result = generator.generate(report)  # must not raise
        assert result.has_failures is True


# ---------------------------------------------------------------------------
# Prompt builder integration
# ---------------------------------------------------------------------------

class TestPromptBuilderIntegration:
    def test_prompt_contains_agent_source(self) -> None:
        call_log = []
        mock = MockLlmProvider(
            response_content=valid_response_json(),
            call_log=call_log
        )
        agent = make_agent("def my_unique_function(): pass")
        generator = LlmPatchGenerator(mock)
        generator.generate_for_gap(make_gap(), agent)
        assert "my_unique_function" in call_log[0].prompt

    def test_prompt_contains_gap_category(self) -> None:
        call_log = []
        mock = MockLlmProvider(response_content=valid_response_json(), call_log=call_log)
        generator = LlmPatchGenerator(mock)
        generator.generate_for_gap(make_gap(HookCategory.BUDGET_EXHAUSTED), make_agent())
        assert "budget_exhausted" in call_log[0].prompt.lower()

    def test_custom_prompt_builder_used(self) -> None:
        from awcp_instrumentation.application.generator.prompt_builder import PromptBuilder
        custom_builder = PromptBuilder(max_tokens=512, temperature=0.1)
        call_log = []
        mock = MockLlmProvider(response_content=valid_response_json(), call_log=call_log)
        generator = LlmPatchGenerator(mock, prompt_builder=custom_builder)
        generator.generate_for_gap(make_gap(), make_agent())
        assert call_log[0].max_tokens == 512
        assert call_log[0].temperature == pytest.approx(0.1)
