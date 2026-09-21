"""Command-line interface for heic-jpg-tidy."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from .image_hash import calculate_phash_distance
from .models import Decision, RuleConfig
from .quarantine import paths_overlap, quarantine_file
from .reporter import (
    write_evaluation_report,
    write_quarantine_action_log,
)
from .scanner import find_file_groups
from .workflow import evaluate_groups


def build_parser() -> argparse.ArgumentParser:
    """Build and return the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="heic-jpg-tidy",
        description=(
            "Conservatively identify redundant JPG copies of HEIC/HEIF images "
            "and optionally move confirmed JPG candidates to quarantine."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    scan_parser = subparsers.add_parser(
        "scan",
        help="Scan a photo archive and write an evaluation report.",
        description=(
            "Scan a source directory recursively for HEIC/JPG filename pairs. "
            "The default behavior is dry-run: files are never moved unless "
            "both --apply and --confirm are provided."
        ),
    )

    scan_parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Root directory containing the photo archive to scan.",
    )

    scan_parser.add_argument(
        "--quarantine",
        type=Path,
        required=True,
        help=(
            "Separate root directory where confirmed JPG candidates are moved "
            "when --apply --confirm is used."
        ),
    )

    scan_parser.add_argument(
        "--report-dir",
        type=Path,
        required=True,
        help="Directory where CSV evaluation reports and action logs are written.",
    )

    scan_parser.add_argument(
        "--datetime-tolerance-seconds",
        type=float,
        default=5.0,
        help=("Maximum allowed DateTimeOriginal difference in seconds. Default: 5.0."),
    )

    scan_parser.add_argument(
        "--verify-image-hash",
        action="store_true",
        help=(
            "Enable perceptual image hash verification for pairs that already "
            "pass metadata checks. Requires the optional ImageHash dependency."
        ),
    )

    scan_parser.add_argument(
        "--max-hash-distance",
        type=int,
        default=4,
        help=(
            "Maximum allowed perceptual hash distance when "
            "--verify-image-hash is enabled. Default: 4."
        ),
    )

    scan_parser.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Actually move confirmed JPG candidates to quarantine. Requires --confirm."
        ),
    )

    scan_parser.add_argument(
        "--confirm",
        action="store_true",
        help=("Confirm that --apply should perform real quarantine operations."),
    )

    return parser


def create_report_path(
    report_dir: Path,
    prefix: str,
    timestamp: datetime,
) -> Path:
    """
    Create a unique CSV output path.

    A numeric suffix is added if a report with the same timestamp already
    exists. This avoids accidental overwriting when commands run more than
    once within the same second.
    """
    timestamp_text = timestamp.strftime("%Y%m%d_%H%M%S")
    base_path = report_dir / f"{prefix}_{timestamp_text}.csv"

    if not base_path.exists():
        return base_path

    counter = 1

    while True:
        candidate_path = report_dir / (f"{prefix}_{timestamp_text}_{counter}.csv")

        if not candidate_path.exists():
            return candidate_path

        counter += 1


def validate_arguments(args: argparse.Namespace) -> str | None:
    """
    Validate argument combinations and directory safety requirements.

    Returns:
        An error message if validation fails, otherwise None.
    """
    if args.datetime_tolerance_seconds < 0:
        return "--datetime-tolerance-seconds must be zero or greater."

    if args.max_hash_distance < 0:
        return "--max-hash-distance must be zero or greater."

    if args.apply and not args.confirm:
        return (
            "--apply requires --confirm. "
            "Without both flags the command is always dry-run."
        )

    source_root = args.source.resolve()
    quarantine_root = args.quarantine.resolve()

    if not source_root.is_dir():
        return f"Source directory does not exist or is not a directory: {source_root}"

    if paths_overlap(source_root, quarantine_root):
        return (
            "Source and quarantine directories overlap. "
            "The quarantine directory must be completely separate from the "
            "source directory."
        )

    return None


def print_summary(
    *,
    evaluation_count: int,
    candidate_count: int,
    ambiguous_group_count: int,
    report_path: Path,
    apply_mode: bool,
) -> None:
    """Print a short summary after evaluation."""
    print()
    print("Evaluation complete")
    print(f"  Evaluated pairs:     {evaluation_count}")
    print(f"  Move candidates:     {candidate_count}")
    print(f"  Ambiguous groups:    {ambiguous_group_count}")
    print(f"  Evaluation report:   {report_path}")

    if not apply_mode:
        print()
        print("Dry-run mode: no files were moved.")
        print("Use --apply --confirm to quarantine confirmed MOVE_CANDIDATE JPG files.")


def run_scan(args: argparse.Namespace) -> int:
    """Run the scan workflow for parsed CLI arguments."""
    validation_error = validate_arguments(args)

    if validation_error is not None:
        print(f"Error: {validation_error}", file=sys.stderr)
        return 2

    source_root = args.source.resolve()
    quarantine_root = args.quarantine.resolve()
    report_dir = args.report_dir.resolve()

    config = RuleConfig(
        datetime_tolerance_seconds=args.datetime_tolerance_seconds,
        verify_image_hash=args.verify_image_hash,
        max_hash_distance=args.max_hash_distance,
    )

    print(f"Scanning source: {source_root}")

    try:
        groups = find_file_groups(source_root)

        workflow_result = evaluate_groups(
            groups,
            config,
            hash_calculator=(
                calculate_phash_distance if args.verify_image_hash else None
            ),
        )

        run_timestamp = datetime.now().astimezone()

        evaluation_report_path = create_report_path(
            report_dir,
            "evaluation",
            run_timestamp,
        )

        write_evaluation_report(
            result=workflow_result,
            source_root=source_root,
            output_path=evaluation_report_path,
        )

    except OSError as error:
        print(
            f"Error: filesystem operation failed: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    candidate_evaluations = tuple(
        evaluation
        for evaluation in workflow_result.evaluations
        if evaluation.decision is Decision.MOVE_CANDIDATE
    )

    print_summary(
        evaluation_count=len(workflow_result.evaluations),
        candidate_count=len(candidate_evaluations),
        ambiguous_group_count=len(workflow_result.ambiguous_groups),
        report_path=evaluation_report_path,
        apply_mode=args.apply,
    )

    if not args.apply:
        return 0

    print()
    print("Apply mode confirmed. Starting quarantine operations...")

    quarantine_results = []

    for evaluation in candidate_evaluations:
        result = quarantine_file(
            source_file=evaluation.pair.jpg.path,
            source_root=source_root,
            quarantine_root=quarantine_root,
        )

        quarantine_results.append(result)

        print(
            f"  {result.status.value:<7} "
            f"{evaluation.pair.jpg.path.name} "
            f"- {result.message}"
        )

    try:
        action_log_path = create_report_path(
            report_dir,
            "quarantine_actions",
            run_timestamp,
        )

        write_quarantine_action_log(
            results=quarantine_results,
            source_root=source_root,
            quarantine_root=quarantine_root,
            output_path=action_log_path,
            timestamp=run_timestamp,
        )

    except OSError as error:
        print(
            f"Error: quarantine actions were completed, but the action log "
            f"could not be written: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1

    moved_count = sum(result.status.value == "MOVED" for result in quarantine_results)
    skipped_count = sum(
        result.status.value == "SKIPPED" for result in quarantine_results
    )
    error_count = sum(result.status.value == "ERROR" for result in quarantine_results)

    print()
    print("Quarantine complete")
    print(f"  Moved:        {moved_count}")
    print(f"  Skipped:      {skipped_count}")
    print(f"  Errors:       {error_count}")
    print(f"  Action log:   {action_log_path}")

    return 1 if error_count else 0


def main(argv: list[str] | None = None) -> int:
    """
    Run the command-line application.

    Args:
        argv:
            Optional argument list, excluding the executable name.
            None means arguments are read from sys.argv.

    Returns:
        Process exit code.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        return run_scan(args)

    parser.error(f"Unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
