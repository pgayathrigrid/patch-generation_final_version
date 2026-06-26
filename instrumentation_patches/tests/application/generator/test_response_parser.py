from __future__ import annotations
"""Tests for ResponseParser — JSON parsing and failure handling."""

import json

import pytest

from awcp_instrumentation.application.generator.llm_interface import LlmResponse
from awcp_instrumentation.application.generator.models import InsertionLocation
from awcp_instrumentation.application.generator.response_parser import (
    ResponseParseError,
    ResponseParser,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_response(content: str) -> LlmResponse:
    return LlmResponse(
        content=content, model="test-model",
        prompt_tokens=10, completion_tokens=20
    )


def valid_json(
    changes: list | None = None,
    import_additions: list | None = None,
    explanation: str = "added hook",
    confidence: float = 0.9,
) -> str:
    if changes is None:
        changes = [
            {
                "code_fragment": "logger.info('decision')",
                "location": "before_function_body",
                "target_function": "run",
                "explanation": "log at entry",
            }
        ]
    return json.dumps({
        "import_additions": import_additions if import_additions is not None else ["import logging"],
        "changes": changes,
        "explanation": explanation,
        "confidence": confidence,
    })


PARSER = ResponseParser()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestResponseParserSuccess:
    def test_parses_valid_json(self) -> None:
        result = PARSER.parse(make_response(valid_json()))
        assert result is not None

    def test_extracts_import_additions(self) -> None:
        result = PARSER.parse(make_response(valid_json(import_additions=["import logging"])))
        assert "import logging" in result.import_additions

    def test_extracts_explanation(self) -> None:
        result = PARSER.parse(make_response(valid_json(explanation="added observability")))
        assert result.explanation == "added observability"

    def test_extracts_confidence(self) -> None:
        result = PARSER.parse(make_response(valid_json(confidence=0.75)))
        assert result.confidence == pytest.approx(0.75)

    def test_extracts_change_code_fragment(self) -> None:
        result = PARSER.parse(make_response(valid_json()))
        assert result.changes[0].code_fragment == "logger.info('decision')"

    def test_extracts_change_location(self) -> None:
        result = PARSER.parse(make_response(valid_json()))
        assert result.changes[0].location == InsertionLocation.BEFORE_FUNCTION_BODY

    def test_extracts_change_target_function(self) -> None:
        result = PARSER.parse(make_response(valid_json()))
        assert result.changes[0].target_function == "run"

    def test_target_function_null_becomes_none(self) -> None:
        change = {
            "code_fragment": "import logging",
            "location": "after_imports",
            "target_function": None,
            "explanation": "add import"
        }
        result = PARSER.parse(make_response(valid_json(changes=[change])))
        assert result.changes[0].target_function is None

    def test_empty_target_function_string_becomes_none(self) -> None:
        change = {
            "code_fragment": "x = 1",
            "location": "top_of_file",
            "target_function": "",
            "explanation": "top level"
        }
        result = PARSER.parse(make_response(valid_json(changes=[change])))
        assert result.changes[0].target_function is None

    def test_multiple_changes_parsed(self) -> None:
        changes = [
            {"code_fragment": "import logging", "location": "after_imports",
             "target_function": None, "explanation": "import"},
            {"code_fragment": "logger.info('x')", "location": "before_function_body",
             "target_function": "run", "explanation": "log"},
        ]
        result = PARSER.parse(make_response(valid_json(changes=changes)))
        assert len(result.changes) == 2

    def test_confidence_clamped_to_zero_one(self) -> None:
        result = PARSER.parse(make_response(valid_json(confidence=1.5)))
        assert result.confidence == 1.0
        result2 = PARSER.parse(make_response(valid_json(confidence=-0.5)))
        assert result2.confidence == 0.0

    def test_empty_import_additions_allowed(self) -> None:
        result = PARSER.parse(make_response(valid_json(import_additions=[])))
        assert result.import_additions == []

    def test_strips_whitespace_from_imports(self) -> None:
        result = PARSER.parse(make_response(valid_json(import_additions=["  import logging  "])))
        assert "import logging" in result.import_additions

    def test_all_insertion_locations_parseable(self) -> None:
        for loc in InsertionLocation:
            change = {
                "code_fragment": "pass",
                "location": loc.value,
                "target_function": None,
                "explanation": "test"
            }
            result = PARSER.parse(make_response(valid_json(changes=[change])))
            assert result.changes[0].location == loc


# ---------------------------------------------------------------------------
# Markdown fence stripping
# ---------------------------------------------------------------------------

class TestMarkdownFenceStripping:
    def test_strips_json_code_fence(self) -> None:
        wrapped = f"```json\n{valid_json()}\n```"
        result = PARSER.parse(make_response(wrapped))
        assert result.explanation == "added hook"

    def test_strips_plain_code_fence(self) -> None:
        wrapped = f"```\n{valid_json()}\n```"
        result = PARSER.parse(make_response(wrapped))
        assert result.explanation == "added hook"


# ---------------------------------------------------------------------------
# Failure cases — ResponseParseError expected
# ---------------------------------------------------------------------------

class TestResponseParserFailures:
    def test_empty_response_raises(self) -> None:
        with pytest.raises(ResponseParseError, match="empty"):
            PARSER.parse(make_response(""))

    def test_whitespace_only_response_raises(self) -> None:
        with pytest.raises(ResponseParseError):
            PARSER.parse(make_response("   \n  "))

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(ResponseParseError, match="JSON"):
            PARSER.parse(make_response("this is not json"))

    def test_missing_changes_field_raises(self) -> None:
        data = json.dumps({"import_additions": [], "explanation": "x", "confidence": 0.5})
        with pytest.raises(ResponseParseError, match="changes"):
            PARSER.parse(make_response(data))

    def test_unknown_location_raises(self) -> None:
        change = {
            "code_fragment": "pass",
            "location": "unknown_location",
            "target_function": None,
            "explanation": "x"
        }
        with pytest.raises(ResponseParseError, match="location"):
            PARSER.parse(make_response(valid_json(changes=[change])))

    def test_empty_code_fragment_raises(self) -> None:
        change = {
            "code_fragment": "",
            "location": "inline",
            "target_function": None,
            "explanation": "x"
        }
        with pytest.raises(ResponseParseError, match="code_fragment"):
            PARSER.parse(make_response(valid_json(changes=[change])))

    def test_missing_location_raises(self) -> None:
        change = {"code_fragment": "pass", "target_function": None, "explanation": "x"}
        with pytest.raises(ResponseParseError, match="location"):
            PARSER.parse(make_response(valid_json(changes=[change])))

    def test_changes_not_list_raises(self) -> None:
        data = json.dumps({
            "import_additions": [],
            "changes": "not a list",
            "explanation": "x",
            "confidence": 0.5,
        })
        with pytest.raises(ResponseParseError):
            PARSER.parse(make_response(data))

    def test_json_root_not_object_raises(self) -> None:
        with pytest.raises(ResponseParseError):
            PARSER.parse(make_response(json.dumps([1, 2, 3])))
