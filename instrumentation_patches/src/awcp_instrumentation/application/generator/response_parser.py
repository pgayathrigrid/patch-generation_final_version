"""
LLM response parser for the Patch Generator.

Converts a raw ``LlmResponse`` into a structured list of ``PatchChange``
objects and import additions.  Raises ``ResponseParseError`` when the
response cannot be interpreted, allowing the generator to mark the
corresponding ``PatchProposal`` as FAILED cleanly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from awcp_instrumentation.application.generator.llm_interface import LlmResponse
from awcp_instrumentation.application.generator.models import (
    InsertionLocation,
    PatchChange,
)


# ---------------------------------------------------------------------------
# Public exception
# ---------------------------------------------------------------------------

class ResponseParseError(Exception):
    """
    Raised when an LLM response cannot be parsed into valid patch changes.

    The generator catches this and marks the proposal as ``FAILED`` rather
    than propagating the exception up the call stack.
    """


# ---------------------------------------------------------------------------
# Internal parsed-response container
# ---------------------------------------------------------------------------

@dataclass
class _ParsedResponse:
    changes: List[PatchChange] = field(default_factory=list)
    import_additions: List[str] = field(default_factory=list)
    explanation: str = ""
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# ResponseParser
# ---------------------------------------------------------------------------

class ResponseParser:
    """
    Parses a raw ``LlmResponse`` into structured patch data.

    Strategy:
    1. Attempt to parse the response content as JSON.
    2. If JSON parsing fails or required fields are missing, raise
       ``ResponseParseError`` with a descriptive message.

    The parser intentionally never silently produces empty or garbage output —
    any ambiguity surfaces as an explicit failure so the generator can record
    it accurately in the ``PatchProposal``.
    """

    def parse(self, response: LlmResponse) -> _ParsedResponse:
        """
        Parse *response* into a ``_ParsedResponse``.

        Args:
            response: The ``LlmResponse`` returned by the provider.

        Returns:
            A ``_ParsedResponse`` with structured changes and metadata.

        Raises:
            ResponseParseError: If the content cannot be parsed or is invalid.
        """
        content = response.content.strip()
        if not content:
            raise ResponseParseError("LLM returned an empty response.")

        data = self._extract_json(content)
        return self._build_parsed_response(data)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(content: str) -> Dict[str, Any]:
        """
        Extract a JSON object from *content*.

        Handles responses that may be wrapped in markdown fences
        (```json ... ```) even though the prompt explicitly forbids them,
        because some providers add them anyway.
        """
        text = content

        # Strip markdown code fences if present
        if "```" in text:
            lines = text.splitlines()
            stripped = [
                ln for ln in lines
                if not ln.strip().startswith("```")
            ]
            text = "\n".join(stripped).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ResponseParseError(
                f"Response is not valid JSON: {exc.msg} at line {exc.lineno}."
            ) from exc

    @staticmethod
    def _parse_location(raw: str) -> InsertionLocation:
        try:
            return InsertionLocation(raw)
        except ValueError:
            raise ResponseParseError(
                f"Unknown insertion location '{raw}'. "
                f"Valid values: {[e.value for e in InsertionLocation]}"
            )

    def _build_parsed_response(self, data: Dict[str, Any]) -> _ParsedResponse:
        if not isinstance(data, dict):
            raise ResponseParseError("JSON response root must be an object.")

        # --- import_additions ---
        raw_imports = data.get("import_additions", [])
        if not isinstance(raw_imports, list):
            raise ResponseParseError("'import_additions' must be a list.")
        import_additions = [str(i).strip() for i in raw_imports if str(i).strip()]

        # --- changes ---
        raw_changes = data.get("changes")
        if raw_changes is None:
            raise ResponseParseError("Response missing required field 'changes'.")
        if not isinstance(raw_changes, list):
            raise ResponseParseError("'changes' must be a list.")

        changes: List[PatchChange] = []
        for idx, raw_change in enumerate(raw_changes):
            changes.append(self._parse_change(raw_change, idx))

        # --- explanation ---
        explanation = str(data.get("explanation", "")).strip()

        # --- confidence ---
        raw_confidence = data.get("confidence", 0.0)
        try:
            confidence = float(raw_confidence)
            confidence = max(0.0, min(1.0, confidence))
        except (TypeError, ValueError):
            confidence = 0.0

        return _ParsedResponse(
            changes=changes,
            import_additions=import_additions,
            explanation=explanation,
            confidence=confidence,
        )

    def _parse_change(self, raw: Any, index: int) -> PatchChange:
        if not isinstance(raw, dict):
            raise ResponseParseError(f"Change at index {index} must be an object.")

        code_fragment = raw.get("code_fragment")
        if not code_fragment or not str(code_fragment).strip():
            raise ResponseParseError(
                f"Change at index {index} has empty or missing 'code_fragment'."
            )

        raw_location = raw.get("location")
        if not raw_location:
            raise ResponseParseError(
                f"Change at index {index} missing required field 'location'."
            )
        location = self._parse_location(str(raw_location))

        target_function: Optional[str] = raw.get("target_function") or None
        if target_function:
            target_function = str(target_function).strip() or None

        explanation = str(raw.get("explanation", "")).strip()

        return PatchChange(
            code_fragment=str(code_fragment).strip(),
            location=location,
            target_function=target_function,
            explanation=explanation,
        )
