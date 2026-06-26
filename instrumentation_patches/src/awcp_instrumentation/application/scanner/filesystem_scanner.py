from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Set

from awcp_instrumentation.application.scanner.interface import AgentScanner
from awcp_instrumentation.application.scanner.result import RepositoryScanResult, ScanError
from awcp_instrumentation.domain.entities.agent_source import AgentSource

# Directories excluded by default — these never contain agent code.
_DEFAULT_EXCLUDE_DIRS: Set[str] = {
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    "eggs",
    ".eggs",
    "site-packages",
}


class FilesystemScanner(AgentScanner):
    """
    Concrete scanner that discovers Python agent files on the local filesystem.

    Handles two modes:
    - Single file: wraps the file directly into an ``AgentSource``.
    - Directory:   walks the tree recursively, collecting all ``.py`` files
                   while honouring the exclusion list.

    Files that cannot be read (permission errors, encoding issues) are captured
    as ``ScanError`` records rather than raising exceptions.

    Args:
        exclude_dirs: Additional directory names to skip during recursive
                      traversal.  Combined with the built-in defaults.
    """

    def __init__(self, exclude_dirs: Optional[List[str]] = None) -> None:
        self._exclude_dirs: Set[str] = _DEFAULT_EXCLUDE_DIRS.copy()
        if exclude_dirs:
            self._exclude_dirs.update(exclude_dirs)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(self, target: Path) -> RepositoryScanResult:
        """
        Scan *target* (file or directory) and return a ``RepositoryScanResult``.

        Args:
            target: Path to a ``.py`` file or a directory.

        Returns:
            ``RepositoryScanResult`` populated with agents and/or errors.

        Raises:
            ValueError: If *target* does not exist.
        """
        if not target.exists():
            raise ValueError(f"Scan target does not exist: {target}")

        if target.is_file():
            return self._scan_single_file(target)

        return self._scan_directory(target)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _scan_single_file(self, path: Path) -> RepositoryScanResult:
        agents: List[AgentSource] = []
        errors: List[ScanError] = []

        if path.suffix != ".py":
            return RepositoryScanResult(
                target=path,
                agents=[],
                scanned_files=0,
                skipped_files=1,
                errors=[ScanError(path=path, reason="Not a Python file (.py required)")],
            )

        agent, error = self._load_agent(path)
        if agent is not None:
            agents.append(agent)
        if error is not None:
            errors.append(error)

        return RepositoryScanResult(
            target=path,
            agents=agents,
            scanned_files=1 if error is None else 0,
            skipped_files=0,
            errors=errors,
        )

    def _scan_directory(self, directory: Path) -> RepositoryScanResult:
        agents: List[AgentSource] = []
        errors: List[ScanError] = []
        scanned = 0
        skipped = 0

        for py_file in self._iter_python_files(directory):
            agent, error = self._load_agent(py_file)
            if agent is not None:
                agents.append(agent)
                scanned += 1
            if error is not None:
                errors.append(error)
                scanned += 1  # attempted but failed — still counts as encountered

        # Count skipped: all .py files under excluded dirs
        for excluded_path in self._iter_excluded_python_files(directory):
            del excluded_path  # we only need the count
            skipped += 1

        return RepositoryScanResult(
            target=directory,
            agents=agents,
            scanned_files=scanned,
            skipped_files=skipped,
            errors=errors,
        )

    def _iter_python_files(self, directory: Path):
        """Yield .py files under *directory*, skipping excluded dirs."""
        for entry in sorted(directory.rglob("*.py")):
            if self._is_excluded(entry):
                continue
            if entry.is_file():
                yield entry

    def _iter_excluded_python_files(self, directory: Path):
        """Yield .py files that sit inside excluded directories."""
        for entry in sorted(directory.rglob("*.py")):
            if self._is_excluded(entry) and entry.is_file():
                yield entry

    def _is_excluded(self, path: Path) -> bool:
        """Return True if *path* is inside any excluded directory."""
        return any(part in self._exclude_dirs for part in path.parts)

    @staticmethod
    def _load_agent(path: Path) -> tuple[Optional[AgentSource], Optional[ScanError]]:
        """
        Attempt to create an ``AgentSource`` from *path*.

        Returns a (agent, None) tuple on success or (None, error) on failure.
        """
        try:
            return AgentSource.from_path(path), None
        except PermissionError:
            return None, ScanError(path=path, reason="Permission denied")
        except UnicodeDecodeError as exc:
            return None, ScanError(path=path, reason=f"Encoding error: {exc.reason}")
        except OSError as exc:
            return None, ScanError(path=path, reason=f"OS error: {exc.strerror}")
