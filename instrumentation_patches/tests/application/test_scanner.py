"""Tests for the Repository Scanner module."""

from pathlib import Path

import pytest

from awcp_instrumentation.application.scanner import (
    FilesystemScanner,
    RepositoryScanResult,
    ScanError,
)
from awcp_instrumentation.application.scanner.interface import AgentScanner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_py(directory: Path, name: str, content: str = "x = 1") -> Path:
    """Write a .py file into *directory* and return the path."""
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


def make_dir(parent: Path, name: str) -> Path:
    d = parent / name
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Interface contract
# ---------------------------------------------------------------------------

class TestAgentScannerInterface:
    def test_filesystem_scanner_is_agent_scanner(self) -> None:
        assert isinstance(FilesystemScanner(), AgentScanner)

    def test_scan_returns_repository_scan_result(self, tmp_path: Path) -> None:
        write_py(tmp_path, "agent.py")
        result = FilesystemScanner().scan(tmp_path)
        assert isinstance(result, RepositoryScanResult)


# ---------------------------------------------------------------------------
# Single-file scanning
# ---------------------------------------------------------------------------

class TestSingleFileScan:
    def test_loads_python_file(self, tmp_path: Path) -> None:
        path = write_py(tmp_path, "my_agent.py", "print('hello')")
        result = FilesystemScanner().scan(path)

        assert result.agent_count == 1
        assert result.agents[0].source_code == "print('hello')"
        assert result.agents[0].agent_name == "my_agent"

    def test_target_is_the_file_path(self, tmp_path: Path) -> None:
        path = write_py(tmp_path, "agent.py")
        result = FilesystemScanner().scan(path)
        assert result.target == path

    def test_rejects_non_python_file(self, tmp_path: Path) -> None:
        txt = tmp_path / "readme.txt"
        txt.write_text("not python")
        result = FilesystemScanner().scan(txt)

        assert result.agent_count == 0
        assert result.has_errors is True
        assert result.errors[0].path == txt

    def test_raises_for_nonexistent_path(self, tmp_path: Path) -> None:
        missing = tmp_path / "ghost.py"
        with pytest.raises(ValueError, match="does not exist"):
            FilesystemScanner().scan(missing)

    def test_scanned_files_count_is_one(self, tmp_path: Path) -> None:
        path = write_py(tmp_path, "agent.py")
        result = FilesystemScanner().scan(path)
        assert result.scanned_files == 1

    def test_skipped_files_count_is_zero_for_python_file(self, tmp_path: Path) -> None:
        path = write_py(tmp_path, "agent.py")
        result = FilesystemScanner().scan(path)
        assert result.skipped_files == 0


# ---------------------------------------------------------------------------
# Directory scanning
# ---------------------------------------------------------------------------

class TestDirectoryScan:
    def test_discovers_python_files_recursively(self, tmp_path: Path) -> None:
        write_py(tmp_path, "agent_a.py")
        sub = make_dir(tmp_path, "subdir")
        write_py(sub, "agent_b.py")

        result = FilesystemScanner().scan(tmp_path)
        assert result.agent_count == 2

    def test_agent_names_match_file_stems(self, tmp_path: Path) -> None:
        write_py(tmp_path, "alpha.py")
        write_py(tmp_path, "beta.py")

        result = FilesystemScanner().scan(tmp_path)
        assert set(result.agent_names) == {"alpha", "beta"}

    def test_ignores_non_python_files(self, tmp_path: Path) -> None:
        write_py(tmp_path, "agent.py")
        (tmp_path / "notes.txt").write_text("ignore me")
        (tmp_path / "data.json").write_text("{}")

        result = FilesystemScanner().scan(tmp_path)
        assert result.agent_count == 1

    def test_target_is_the_directory(self, tmp_path: Path) -> None:
        write_py(tmp_path, "agent.py")
        result = FilesystemScanner().scan(tmp_path)
        assert result.target == tmp_path

    def test_empty_directory_returns_zero_agents(self, tmp_path: Path) -> None:
        result = FilesystemScanner().scan(tmp_path)
        assert result.agent_count == 0
        assert result.has_errors is False

    def test_scanned_files_counts_successful_loads(self, tmp_path: Path) -> None:
        write_py(tmp_path, "a.py")
        write_py(tmp_path, "b.py")
        result = FilesystemScanner().scan(tmp_path)
        assert result.scanned_files == 2


# ---------------------------------------------------------------------------
# Exclusion rules
# ---------------------------------------------------------------------------

class TestExclusionRules:
    def test_skips_venv_directory(self, tmp_path: Path) -> None:
        venv = make_dir(tmp_path, ".venv")
        write_py(venv, "conftest.py")
        write_py(tmp_path, "real_agent.py")

        result = FilesystemScanner().scan(tmp_path)
        assert result.agent_count == 1
        assert result.agent_names == ["real_agent"]

    def test_skips_pycache_directory(self, tmp_path: Path) -> None:
        cache = make_dir(tmp_path, "__pycache__")
        write_py(cache, "cached.py")
        write_py(tmp_path, "agent.py")

        result = FilesystemScanner().scan(tmp_path)
        assert result.agent_count == 1

    def test_skips_git_directory(self, tmp_path: Path) -> None:
        git = make_dir(tmp_path, ".git")
        write_py(git, "hook.py")
        write_py(tmp_path, "agent.py")

        result = FilesystemScanner().scan(tmp_path)
        assert result.agent_count == 1

    def test_custom_exclude_dirs_are_respected(self, tmp_path: Path) -> None:
        vendor = make_dir(tmp_path, "vendor")
        write_py(vendor, "third_party.py")
        write_py(tmp_path, "agent.py")

        scanner = FilesystemScanner(exclude_dirs=["vendor"])
        result = scanner.scan(tmp_path)
        assert result.agent_count == 1
        assert result.agent_names == ["agent"]

    def test_skipped_files_count_reflects_excluded_dirs(self, tmp_path: Path) -> None:
        venv = make_dir(tmp_path, ".venv")
        write_py(venv, "excluded.py")
        write_py(tmp_path, "included.py")

        result = FilesystemScanner().scan(tmp_path)
        assert result.skipped_files == 1
        assert result.agent_count == 1

    def test_default_excludes_do_not_prevent_custom_dirs(self, tmp_path: Path) -> None:
        my_agents = make_dir(tmp_path, "my_agents")
        write_py(my_agents, "bot.py")

        result = FilesystemScanner().scan(tmp_path)
        assert result.agent_count == 1


# ---------------------------------------------------------------------------
# Source code fidelity
# ---------------------------------------------------------------------------

class TestSourceFidelity:
    def test_source_code_preserved_exactly(self, tmp_path: Path) -> None:
        source = "def run():\n    return 42\n"
        path = write_py(tmp_path, "agent.py", source)
        result = FilesystemScanner().scan(path)
        assert result.agents[0].source_code == source

    def test_multifile_source_codes_are_independent(self, tmp_path: Path) -> None:
        write_py(tmp_path, "a.py", "A = 1")
        write_py(tmp_path, "b.py", "B = 2")

        result = FilesystemScanner().scan(tmp_path)
        sources = {a.agent_name: a.source_code for a in result.agents}
        assert sources["a"] == "A = 1"
        assert sources["b"] == "B = 2"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    def test_scan_error_has_path_and_reason(self, tmp_path: Path) -> None:
        txt = tmp_path / "bad.txt"
        txt.write_text("not python")
        result = FilesystemScanner().scan(txt)

        error = result.errors[0]
        assert isinstance(error, ScanError)
        assert error.path == txt
        assert isinstance(error.reason, str)
        assert len(error.reason) > 0

    def test_no_errors_on_clean_directory(self, tmp_path: Path) -> None:
        write_py(tmp_path, "agent.py")
        result = FilesystemScanner().scan(tmp_path)
        assert result.has_errors is False
        assert result.errors == []

    def test_has_errors_property_true_when_errors_present(self, tmp_path: Path) -> None:
        txt = tmp_path / "bad.txt"
        txt.write_text("nope")
        result = FilesystemScanner().scan(txt)
        assert result.has_errors is True
