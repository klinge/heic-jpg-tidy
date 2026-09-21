# src/heic_jpg_tidy/models.py
"""Domain models used by heic-jpg-tidy."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class Decision(str, Enum):
    """Possible outcomes when evaluating a HEIC/JPG pair."""

    MOVE_CANDIDATE = "MOVE_CANDIDATE"
    REVIEW = "REVIEW"


class ReasonCode(str, Enum):
    """Machine-readable reasons for an evaluation result."""

    MULTIPLE_MATCHING_FILES = "MULTIPLE_MATCHING_FILES"
    IMAGE_READ_ERROR = "IMAGE_READ_ERROR"

    DATETIME_MISSING = "DATETIME_MISSING"
    DATETIME_MISMATCH = "DATETIME_MISMATCH"

    CAMERA_MAKE_MISMATCH = "CAMERA_MAKE_MISMATCH"
    CAMERA_MODEL_MISMATCH = "CAMERA_MODEL_MISMATCH"

    DIMENSIONS_MISSING = "DIMENSIONS_MISSING"
    DIMENSIONS_MISMATCH = "DIMENSIONS_MISMATCH"

    IMAGE_HASH_ERROR = "IMAGE_HASH_ERROR"
    IMAGE_HASH_MISMATCH = "IMAGE_HASH_MISMATCH"

    MATCH_CONFIRMED = "MATCH_CONFIRMED"


@dataclass(frozen=True)
class ImageInfo:
    """Selected metadata and properties read from an image file."""

    path: Path
    width: int | None = None
    height: int | None = None
    datetime_original: datetime | None = None
    make: str | None = None
    model: str | None = None
    read_error: str | None = None


@dataclass(frozen=True)
class FileGroup:
    """Files with the same normalized filename stem in one directory."""

    directory: Path
    stem: str
    heic_paths: tuple[Path, ...] = field(default_factory=tuple)
    jpg_paths: tuple[Path, ...] = field(default_factory=tuple)

    @property
    def is_unambiguous_pair(self) -> bool:
        """Return True when the group contains exactly one HEIC and one JPG."""
        return len(self.heic_paths) == 1 and len(self.jpg_paths) == 1


@dataclass(frozen=True)
class CandidatePair:
    """One potential HEIC/JPG pair in the same directory."""

    heic: ImageInfo
    jpg: ImageInfo


@dataclass(frozen=True)
class WorkflowResult:
    """Results produced when evaluating discovered file groups."""

    evaluations: tuple[EvaluationResult, ...] = field(default_factory=tuple)
    ambiguous_groups: tuple[FileGroup, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class RuleConfig:
    """Configuration controlling pair evaluation."""

    datetime_tolerance_seconds: float = 5.0
    verify_image_hash: bool = False
    max_hash_distance: int = 4


@dataclass(frozen=True)
class EvaluationResult:
    """The result of evaluating one potential HEIC/JPG pair."""

    pair: CandidatePair
    decision: Decision
    reason_codes: tuple[ReasonCode, ...]
    details: tuple[str, ...] = field(default_factory=tuple)

    datetime_difference_seconds: float | None = None
    make_match: bool | None = None
    model_match: bool | None = None
    dimensions_match: bool | None = None
    image_hash_distance: int | None = None


class QuarantineStatus(str, Enum):
    """Possible outcomes of a quarantine operation."""

    MOVED = "MOVED"
    SKIPPED = "SKIPPED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class QuarantineResult:
    """Result of one attempted quarantine operation."""

    status: QuarantineStatus
    source_path: Path
    quarantine_path: Path
    message: str
    source_sha256: str | None = None
    quarantine_sha256: str | None = None
