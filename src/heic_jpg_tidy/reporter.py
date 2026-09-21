"""CSV reporting for HEIC/JPG evaluation results."""

from __future__ import annotations

import csv
import html
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import TypedDict

from .models import (
    Decision,
    EvaluationResult,
    FileGroup,
    QuarantineResult,
    ReasonCode,
    WorkflowResult,
)

REPORT_FIELDNAMES: tuple[str, ...] = (
    "decision",
    "reason_codes",
    "details",
    "heic_path",
    "jpg_path",
    "heic_file_count",
    "jpg_file_count",
    "heic_datetime_original",
    "jpg_datetime_original",
    "datetime_difference_seconds",
    "heic_make",
    "jpg_make",
    "make_match",
    "heic_model",
    "jpg_model",
    "model_match",
    "heic_dimensions",
    "jpg_dimensions",
    "dimensions_match",
    "image_hash_distance",
)


class ReportRow(TypedDict):
    """One row in the CSV evaluation report."""

    decision: str
    reason_codes: str
    details: str
    heic_path: str
    jpg_path: str
    heic_file_count: str
    jpg_file_count: str
    heic_datetime_original: str
    jpg_datetime_original: str
    datetime_difference_seconds: str
    heic_make: str
    jpg_make: str
    make_match: str
    heic_model: str
    jpg_model: str
    model_match: str
    heic_dimensions: str
    jpg_dimensions: str
    dimensions_match: str
    image_hash_distance: str


ACTION_LOG_FIELDNAMES: tuple[str, ...] = (
    "timestamp",
    "status",
    "source_path",
    "quarantine_path",
    "message",
    "source_sha256",
    "quarantine_sha256",
)


class ActionLogRow(TypedDict):
    """One row in the quarantine action log."""

    timestamp: str
    status: str
    source_path: str
    quarantine_path: str
    message: str
    source_sha256: str
    quarantine_sha256: str


def format_datetime(value: datetime | None) -> str:
    """Format a datetime-like value for the CSV report."""
    if value is None:
        return ""

    return value.strftime("%Y-%m-%d %H:%M:%S")


def format_dimensions(width: int | None, height: int | None) -> str:
    """Format dimensions as WIDTHxHEIGHT, or return an empty string."""
    if width is None or height is None:
        return ""

    return f"{width}x{height}"


def format_optional_bool(value: bool | None) -> str:
    """
    Format an optional boolean for CSV output.

    True  -> TRUE
    False -> FALSE
    None  -> UNKNOWN
    """
    if value is True:
        return "TRUE"

    if value is False:
        return "FALSE"

    return "UNKNOWN"


def relative_path_string(path: Path, source_root: Path) -> str:
    """
    Return a path relative to the scanned source root where possible.

    A full path is returned as a fallback if the path is outside source_root.
    """
    try:
        return html.escape(str(path.relative_to(source_root)))
    except ValueError:
        return html.escape(str(path))


def join_paths(paths: tuple[Path, ...], source_root: Path) -> str:
    """Join multiple relative paths for a single CSV cell."""
    return " | ".join(relative_path_string(path, source_root) for path in paths)


def evaluation_to_row(
    evaluation: EvaluationResult,
    source_root: Path,
) -> ReportRow:
    """Convert one evaluated HEIC/JPG pair to a CSV row."""
    heic = evaluation.pair.heic
    jpg = evaluation.pair.jpg

    return {
        "decision": evaluation.decision.value,
        "reason_codes": "|".join(
            reason_code.value for reason_code in evaluation.reason_codes
        ),
        "details": " | ".join(evaluation.details),
        "heic_path": relative_path_string(heic.path, source_root),
        "jpg_path": relative_path_string(jpg.path, source_root),
        "heic_file_count": "1",
        "jpg_file_count": "1",
        "heic_datetime_original": format_datetime(heic.datetime_original),
        "jpg_datetime_original": format_datetime(jpg.datetime_original),
        "datetime_difference_seconds": (
            f"{evaluation.datetime_difference_seconds:.3f}"
            if evaluation.datetime_difference_seconds is not None
            else ""
        ),
        "heic_make": heic.make or "",
        "jpg_make": jpg.make or "",
        "make_match": format_optional_bool(evaluation.make_match),
        "heic_model": heic.model or "",
        "jpg_model": jpg.model or "",
        "model_match": format_optional_bool(evaluation.model_match),
        "heic_dimensions": format_dimensions(heic.width, heic.height),
        "jpg_dimensions": format_dimensions(jpg.width, jpg.height),
        "dimensions_match": format_optional_bool(evaluation.dimensions_match),
        "image_hash_distance": (
            str(evaluation.image_hash_distance)
            if evaluation.image_hash_distance is not None
            else ""
        ),
    }


def ambiguous_group_to_row(
    group: FileGroup,
    source_root: Path,
) -> ReportRow:
    """
    Convert an ambiguous file group to a REVIEW CSV row.

    No metadata is available because the workflow intentionally does not read
    files from ambiguous groups.
    """
    return {
        "decision": Decision.REVIEW.value,
        "reason_codes": ReasonCode.MULTIPLE_MATCHING_FILES.value,
        "details": (
            "The filename group does not contain exactly one HEIC/HEIF file "
            "and exactly one JPG/JPEG file. No automatic action is allowed."
        ),
        "heic_path": join_paths(group.heic_paths, source_root),
        "jpg_path": join_paths(group.jpg_paths, source_root),
        "heic_file_count": str(len(group.heic_paths)),
        "jpg_file_count": str(len(group.jpg_paths)),
        "heic_datetime_original": "",
        "jpg_datetime_original": "",
        "datetime_difference_seconds": "",
        "heic_make": "",
        "jpg_make": "",
        "make_match": "UNKNOWN",
        "heic_model": "",
        "jpg_model": "",
        "model_match": "UNKNOWN",
        "heic_dimensions": "",
        "jpg_dimensions": "",
        "dimensions_match": "UNKNOWN",
        "image_hash_distance": "",
    }


def workflow_result_to_rows(
    result: WorkflowResult,
    source_root: Path,
) -> list[ReportRow]:
    """
    Convert a complete workflow result to report rows.

    Evaluation rows are listed first, followed by ambiguous groups. The
    workflow and scanner already provide deterministic ordering.
    """
    rows = [
        evaluation_to_row(evaluation, source_root) for evaluation in result.evaluations
    ]

    rows.extend(
        ambiguous_group_to_row(group, source_root) for group in result.ambiguous_groups
    )

    return rows


def write_evaluation_report(
    result: WorkflowResult,
    source_root: Path,
    output_path: Path,
) -> int:
    """
    Write a CSV evaluation report and return the number of written rows.

    The file uses UTF-8 with BOM (utf-8-sig). This is still valid UTF-8 and
    makes CSV files open correctly in Excel on many Windows installations.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = workflow_result_to_rows(result, source_root)

    with output_path.open(
        mode="w",
        newline="",
        encoding="utf-8-sig",
    ) as report_file:
        writer = csv.DictWriter(
            report_file,
            fieldnames=REPORT_FIELDNAMES,
            extrasaction="raise",
        )
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)


def format_timestamp(value: datetime) -> str:
    """
    Format an action timestamp in ISO 8601 format.

    The timestamp includes the local UTC offset when the supplied datetime
    is timezone-aware.
    """
    return value.isoformat(timespec="seconds")


def action_result_to_row(
    result: QuarantineResult,
    source_root: Path,
    quarantine_root: Path,
    timestamp: datetime,
) -> ActionLogRow:
    """Convert one QuarantineResult to a CSV action-log row."""
    return {
        "timestamp": format_timestamp(timestamp),
        "status": result.status.value,
        "source_path": relative_path_string(result.source_path, source_root),
        "quarantine_path": relative_path_string(
            result.quarantine_path,
            quarantine_root,
        ),
        "message": result.message,
        "source_sha256": result.source_sha256 or "",
        "quarantine_sha256": result.quarantine_sha256 or "",
    }


def write_quarantine_action_log(
    results: Iterable[QuarantineResult],
    source_root: Path,
    quarantine_root: Path,
    output_path: Path,
    *,
    timestamp: datetime | None = None,
) -> int:
    """
    Write a CSV log of quarantine operations.

    The timestamp represents when this action log was written. All rows in
    one log receive the same timestamp because they belong to the same apply
    operation.

    Returns:
        The number of written action rows.
    """
    log_timestamp = timestamp or datetime.now().astimezone()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = [
        action_result_to_row(
            result,
            source_root,
            quarantine_root,
            log_timestamp,
        )
        for result in results
    ]

    with output_path.open(
        mode="w",
        newline="",
        encoding="utf-8-sig",
    ) as log_file:
        writer = csv.DictWriter[str](
            log_file,
            fieldnames=ACTION_LOG_FIELDNAMES,
            extrasaction="raise",
        )
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)
