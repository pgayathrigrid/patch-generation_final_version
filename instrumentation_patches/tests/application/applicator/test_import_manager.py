"""Tests for ImportManager."""
from __future__ import annotations

import pytest

from awcp_instrumentation.application.applicator.import_manager import ImportManager

MGR = ImportManager()

SOURCE_WITH_IMPORTS = """\
import os
import sys
from pathlib import Path

def run():
    pass
"""

SOURCE_NO_IMPORTS = """\
def run():
    pass
"""

SOURCE_ALIAS_IMPORT = """\
import logging as log

def run():
    pass
"""

SOURCE_FROM_IMPORT = """\
from opentelemetry import trace

def run():
    pass
"""


# ---------------------------------------------------------------------------
# filter_new_imports — deduplication
# ---------------------------------------------------------------------------

class TestFilterNewImports:
    def test_passes_genuinely_new_import(self) -> None:
        result = MGR.filter_new_imports(SOURCE_WITH_IMPORTS, ["import json"])
        assert "import json" in result

    def test_filters_exact_duplicate(self) -> None:
        result = MGR.filter_new_imports(SOURCE_WITH_IMPORTS, ["import os"])
        assert result == []

    def test_filters_aliased_duplicate(self) -> None:
        # "import logging as log" in source means "logging" is taken
        result = MGR.filter_new_imports(SOURCE_ALIAS_IMPORT, ["import logging"])
        assert result == []

    def test_filters_from_import_duplicate(self) -> None:
        result = MGR.filter_new_imports(SOURCE_FROM_IMPORT, ["from opentelemetry import trace"])
        assert result == []

    def test_multiple_new_imports_all_returned(self) -> None:
        result = MGR.filter_new_imports(SOURCE_WITH_IMPORTS, ["import json", "import re"])
        assert "import json" in result
        assert "import re" in result

    def test_mixed_new_and_duplicate(self) -> None:
        result = MGR.filter_new_imports(SOURCE_WITH_IMPORTS, ["import os", "import json"])
        assert "import json" in result
        assert "import os" not in result

    def test_empty_candidates_returns_empty(self) -> None:
        assert MGR.filter_new_imports(SOURCE_WITH_IMPORTS, []) == []

    def test_deduplicates_candidates_against_each_other(self) -> None:
        result = MGR.filter_new_imports(SOURCE_NO_IMPORTS, ["import json", "import json"])
        assert result.count("import json") == 1

    def test_strips_whitespace_from_candidates(self) -> None:
        result = MGR.filter_new_imports(SOURCE_WITH_IMPORTS, ["  import json  "])
        assert "import json" in result

    def test_skips_empty_string_candidates(self) -> None:
        result = MGR.filter_new_imports(SOURCE_NO_IMPORTS, ["", "  ", "import json"])
        assert "import json" in result
        assert "" not in result
        assert "  " not in result

    def test_invalid_import_statement_skipped(self) -> None:
        result = MGR.filter_new_imports(SOURCE_NO_IMPORTS, ["not an import"])
        assert result == []

    def test_source_with_syntax_error_accepts_all(self) -> None:
        bad_source = "def broken(:\n    pass\n"
        result = MGR.filter_new_imports(bad_source, ["import json"])
        assert "import json" in result


# ---------------------------------------------------------------------------
# inject_imports — position
# ---------------------------------------------------------------------------

class TestInjectImports:
    def test_injects_after_last_import(self) -> None:
        result = MGR.inject_imports(SOURCE_WITH_IMPORTS, ["import json"])
        lines = result.splitlines()
        # "from pathlib import Path" is line 3; new import should follow
        from_pathlib_idx = next(i for i, l in enumerate(lines) if "from pathlib" in l)
        json_idx = next(i for i, l in enumerate(lines) if "import json" in l)
        assert json_idx == from_pathlib_idx + 1

    def test_injects_at_top_when_no_imports(self) -> None:
        result = MGR.inject_imports(SOURCE_NO_IMPORTS, ["import json"])
        lines = result.splitlines()
        assert "import json" in lines[0]

    def test_returns_source_unchanged_when_empty(self) -> None:
        assert MGR.inject_imports(SOURCE_WITH_IMPORTS, []) == SOURCE_WITH_IMPORTS

    def test_multiple_imports_in_one_block(self) -> None:
        result = MGR.inject_imports(SOURCE_NO_IMPORTS, ["import json", "import re"])
        assert "import json" in result
        assert "import re" in result

    def test_original_code_preserved(self) -> None:
        result = MGR.inject_imports(SOURCE_WITH_IMPORTS, ["import json"])
        assert "def run():" in result
        assert "import os" in result
        assert "import sys" in result

    def test_result_is_valid_python(self) -> None:
        import ast
        result = MGR.inject_imports(SOURCE_WITH_IMPORTS, ["import json"])
        ast.parse(result)  # should not raise
