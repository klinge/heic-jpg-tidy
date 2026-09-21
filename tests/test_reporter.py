"""Tests for CSV report generation."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from heic_jpg_tidy.models import (
    CandidatePair,
    Decision,
    EvaluationResult,
    FileGroup,
    ImageInfo,
    QuarantineResult,
    QuarantineStatus,
    ReasonCode,
    WorkflowResult,
)
from heic_jpg_tidy.reporter import (
    ACTION_LOG_FIELDNAMES,
    REPORT_FIELDNAMES,
    evaluation_to_row,
    write_evaluation_report,
    write_quarantine_action_log,
)

BASE_TIME = datetime(2024, 7, 15, 12, 30, 0)


def make_evaluation() -> EvaluationResult:
    """Create a representative successful evaluation."""
    pair = CandidatePair(
        heic=ImageInfo(
            path=Path("photos/2024/IMG_1234.HEIC"),
            width=4032,
            height=3024,
            datetime_original=BASE_TIME,
            make="Apple",
            model="iPhone 15 Pro",
        ),
        jpg=ImageInfo(
            path=Path("photos/2024/IMG_1234.JPG"),
            width=4032,
            height=3024,
            datetime_original=BASE_TIME,
            make="Apple",
            model="iPhone 15 Pro",
        ),
    )

    return EvaluationResult(
        pair=pair,
        decision=Decision.MOVE_CANDIDATE,
        reason_codes=(ReasonCode.MATCH_CONFIRMED,),
        details=("All configured metadata rules passed.",),
        datetime_difference_seconds=0.0,
        make_match=True,
        model_match=True,
        dimensions_match=True,
    )


def make_ambiguous_group() -> FileGroup:
    """Create a representative ambiguous filename group."""
    return FileGroup(
        directory=Path("photos/2024"),
        stem="img_9999",
        heic_paths=(Path("photos/2024/IMG_9999.HEIC"),),
        jpg_paths=(
            Path("photos/2024/IMG_9999.JPG"),
            Path("photos/2024/IMG_9999.JPEG"),
        ),
    )


def test_evaluation_to_row_uses_relative_paths() -> None:
    evaluation = make_evaluation()

    row = evaluation_to_row(
        evaluation,
        source_root=Path("photos"),
    )

    assert row["decision"] == "MOVE_CANDIDATE"
    assert row["reason_codes"] == "MATCH_CONFIRMED"
    assert row["heic_path"] == "2024/IMG_1234.HEIC"
    assert row["jpg_path"] == "2024/IMG_1234.JPG"
    assert row["heic_dimensions"] == "4032x3024"
    assert row["jpg_dimensions"] == "4032x3024"
    assert row["make_match"] == "TRUE"
    assert row["model_match"] == "TRUE"
    assert row["dimensions_match"] == "TRUE"


def test_evaluation_to_row_preserves_special_characters_in_paths() -> None:
    evaluation = EvaluationResult(
        pair=CandidatePair(
            heic=ImageInfo(path=Path("photos/2024/A&B.HEIC")),
            jpg=ImageInfo(path=Path("photos/2024/A&B.JPG")),
        ),
        decision=Decision.REVIEW,
        reason_codes=(ReasonCode.IMAGE_READ_ERROR,),
    )

    row = evaluation_to_row(
        evaluation,
        source_root=Path("photos"),
    )

    assert row["heic_path"] == "2024/A&B.HEIC"
    assert row["jpg_path"] == "2024/A&B.JPG"


def test_writes_report_with_evaluations_and_ambiguous_groups(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "reports" / "evaluation.csv"

    result = WorkflowResult(
        evaluations=(make_evaluation(),),
        ambiguous_groups=(make_ambiguous_group(),),
    )

    row_count = write_evaluation_report(
        result=result,
        source_root=Path("photos"),
        output_path=output_path,
    )

    assert row_count == 2
    assert output_path.exists()

    with output_path.open(newline="", encoding="utf-8-sig") as report_file:
        rows = list(csv.DictReader(report_file))

    assert len(rows) == 2
    assert tuple(rows[0].keys()) == REPORT_FIELDNAMES

    successful_row = rows[0]
    assert successful_row["decision"] == "MOVE_CANDIDATE"
    assert successful_row["reason_codes"] == "MATCH_CONFIRMED"
    assert successful_row["heic_path"] == "2024/IMG_1234.HEIC"

    ambiguous_row = rows[1]
    assert ambiguous_row["decision"] == "REVIEW"
    assert ambiguous_row["reason_codes"] == "MULTIPLE_MATCHING_FILES"
    assert ambiguous_row["heic_file_count"] == "1"
    assert ambiguous_row["jpg_file_count"] == "2"
    assert ambiguous_row["heic_path"] == "2024/IMG_9999.HEIC"
    assert ambiguous_row["jpg_path"] == ("2024/IMG_9999.JPG | 2024/IMG_9999.JPEG")


def test_report_creates_parent_directory(tmp_path: Path) -> None:
    output_path = tmp_path / "new" / "nested" / "report.csv"

    result = WorkflowResult(
        evaluations=(),
        ambiguous_groups=(),
    )

    row_count = write_evaluation_report(
        result=result,
        source_root=tmp_path,
        output_path=output_path,
    )

    assert row_count == 0
    assert output_path.exists()

    with output_path.open(newline="", encoding="utf-8-sig") as report_file:
        rows = list(csv.DictReader(report_file))

    assert rows == []


def test_writes_quarantine_action_log(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"
    output_path = tmp_path / "reports" / "quarantine_actions.csv"

    moved_result = QuarantineResult(
        status=QuarantineStatus.MOVED,
        source_path=source_root / "2024" / "Vacation" / "IMG_1234.JPG",
        quarantine_path=(quarantine_root / "2024" / "Vacation" / "IMG_1234.JPG"),
        message="File copied, verified, and removed from the source archive.",
        source_sha256="source-hash",
        quarantine_sha256="source-hash",
    )

    skipped_result = QuarantineResult(
        status=QuarantineStatus.SKIPPED,
        source_path=source_root / "2024" / "Vacation" / "IMG_1235.JPG",
        quarantine_path=(quarantine_root / "2024" / "Vacation" / "IMG_1235.JPG"),
        message="Quarantine destination already exists.",
    )

    timestamp = datetime(2026, 9, 21, 15, 30, 0)

    row_count = write_quarantine_action_log(
        results=(moved_result, skipped_result),
        source_root=source_root,
        quarantine_root=quarantine_root,
        output_path=output_path,
        timestamp=timestamp,
    )

    assert row_count == 2
    assert output_path.exists()

    with output_path.open(newline="", encoding="utf-8-sig") as log_file:
        rows = list(csv.DictReader(log_file))

    assert len(rows) == 2
    assert tuple(rows[0].keys()) == ACTION_LOG_FIELDNAMES

    moved_row = rows[0]
    assert moved_row["timestamp"] == "2026-09-21T15:30:00"
    assert moved_row["status"] == "MOVED"
    assert moved_row["source_path"] == str(Path("2024") / "Vacation" / "IMG_1234.JPG")
    assert moved_row["quarantine_path"] == str(
        Path("2024") / "Vacation" / "IMG_1234.JPG"
    )
    assert moved_row["source_sha256"] == "source-hash"
    assert moved_row["quarantine_sha256"] == "source-hash"

    skipped_row = rows[1]
    assert skipped_row["status"] == "SKIPPED"
    assert skipped_row["source_sha256"] == ""
    assert skipped_row["quarantine_sha256"] == ""


def test_action_log_creates_parent_directory_and_supports_empty_results(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "new" / "nested" / "action_log.csv"

    row_count = write_quarantine_action_log(
        results=(),
        source_root=tmp_path / "source",
        quarantine_root=tmp_path / "quarantine",
        output_path=output_path,
        timestamp=datetime(2026, 9, 21, 15, 30, 0),
    )

    assert row_count == 0
    assert output_path.exists()

    with output_path.open(newline="", encoding="utf-8-sig") as log_file:
        rows = list(csv.DictReader(log_file))

    assert rows == []
