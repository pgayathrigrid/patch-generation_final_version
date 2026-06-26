"""
Abstract base for all concrete DetectionRule implementations.

Provides shared helpers wrapping the private AST utilities so every
concrete rule has a consistent, readable API without re-importing internals.
"""
from __future__ import annotations

import ast
from dataclasses import replace
from typing import List, Optional, Set, Tuple

from awcp_instrumentation.application.detector.interface import DetectionRule
from awcp_instrumentation.application.detector.rules import _ast_helpers as _h
from awcp_instrumentation.domain.entities.governance_hook import GovernanceHook


class BaseDetectionRule(DetectionRule):
    """
    Mixin that gives concrete rules access to pre-built AST traversal helpers.

    Subclasses must still implement ``category``, ``required_hooks``, and
    ``detect`` — this base class adds NO detection logic of its own.
    """

    # ------------------------------------------------------------------
    # AST traversal helpers (called by subclasses)
    # ------------------------------------------------------------------

    def _imports(self, tree: ast.Module) -> Set[str]:
        return _h.get_import_names(tree)

    def _call_sites(self, tree: ast.Module) -> List[Tuple[str, int]]:
        return _h.get_all_call_sites(tree)

    def _decorator_sites(self, tree: ast.Module) -> List[Tuple[str, int]]:
        return _h.get_decorator_sites(tree)

    def _try_except_lines(self, tree: ast.Module) -> List[int]:
        return _h.get_try_except_lines(tree)

    # ------------------------------------------------------------------
    # Matching helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _any_import_matches(imports: Set[str], keywords: List[str]) -> Optional[str]:
        """
        Return the first import name that contains any keyword, else ``None``.
        """
        for imp in imports:
            for kw in keywords:
                if kw in imp:
                    return imp
        return None

    @staticmethod
    def _first_matching_call(
        call_sites: List[Tuple[str, int]], keywords: List[str]
    ) -> Optional[Tuple[str, int]]:
        """
        Return the first ``(name, line)`` where the call name contains
        any of *keywords*, else ``None``.
        """
        for name, line in call_sites:
            for kw in keywords:
                if kw in name:
                    return name, line
        return None

    @staticmethod
    def _first_matching_decorator(
        decorator_sites: List[Tuple[str, int]], keywords: List[str]
    ) -> Optional[Tuple[str, int]]:
        """
        Return the first ``(name, line)`` where the decorator name contains
        any of *keywords*, else ``None``.
        """
        for name, line in decorator_sites:
            for kw in keywords:
                if kw in name:
                    return name, line
        return None

    # ------------------------------------------------------------------
    # Hook construction helper
    # ------------------------------------------------------------------

    @staticmethod
    def _found(hook: GovernanceHook, line: int) -> GovernanceHook:
        """Return a copy of *hook* with ``line_number`` set to *line*."""
        return replace(hook, line_number=line)
