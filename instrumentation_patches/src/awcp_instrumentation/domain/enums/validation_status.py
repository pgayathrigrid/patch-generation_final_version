from enum import Enum


class ValidationStatus(str, Enum):
    """Outcome of patch validation for a single hook or the overall report."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    PENDING = "pending"
