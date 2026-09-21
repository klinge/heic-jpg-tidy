"""Tests for the command-line interface."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from heic_jpg_tidy import cli
from heic_jpg_tidy.models import (
    CandidatePair,
    Decision,
    EvaluationResult,
    ImageInfo,
    QuarantineResult,
    QuarantineStatus,
    ReasonCode,
    WorkflowResult,
)


def make_move_candidate(source_root: Path) -> EvaluationResult:
    """Create a minimal confirmed candidate evaluation."""
    pair = CandidatePair(
        heic=ImageInfo(
            path=source_root / "2024" / "IMG_1234.HEIC",
            width=4032,
            height=3024,
        ),
        jpg=ImageInfo(
            path=source_root / "2024" / "IMG_1234.JPG",
            width=4032,
            height=3024,
        ),
    )

    return EvaluationResult(
        pair=pair,
        decision=Decision.MOVE_CANDIDATE,
        reason_codes=(ReasonCode.MATCH_CONFIRMED,),
    )


def test_create_report_path_adds_suffix_when_needed(tmp_path: Path) -> None:
    timestamp = datetime(2026, 9, 21, 15, 30, 0)

    first_path = cli.create_report_path(
        tmp_path,
        "evaluation",
        timestamp,
    )

    assert first_path.name == "evaluation_20260921_153000.csv"

    first_path.touch()

    second_path = cli.create_report_path(
        tmp_path,
        "evaluation",
        timestamp,
    )

    assert second_path.name == "evaluation_20260921_153000_1.csv"


def test_scan_runs_as_dry_run_by_default(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"
    report_dir = tmp_path / "reports"

    source_root.mkdir()
    quarantine_root.mkdir()

    candidate = make_move_candidate(source_root)

    monkeypatch.setattr(cli, "find_file_groups", lambda path: [])

    monkeypatch.setattr(
        cli,
        "evaluate_groups",
        lambda groups, config, hash_calculator=None: WorkflowResult(
            evaluations=(candidate,),
            ambiguous_groups=(),
        ),
    )

    written_reports: list[Path] = []

    def fake_write_evaluation_report(
        result: WorkflowResult,
        source_root: Path,
        output_path: Path,
    ) -> int:
        written_reports.append(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.touch()
        return 1

    monkeypatch.setattr(
        cli,
        "write_evaluation_report",
        fake_write_evaluation_report,
    )

    def failing_quarantine_file(*args: object, **kwargs: object) -> object:
        raise AssertionError("Dry-run must not quarantine files.")

    monkeypatch.setattr(
        cli,
        "quarantine_file",
        failing_quarantine_file,
    )

    exit_code = cli.main(
        [
            "scan",
            "--source",
            str(source_root),
            "--quarantine",
            str(quarantine_root),
            "--report-dir",
            str(report_dir),
        ]
    )

    assert exit_code == 0
    assert len(written_reports) == 1


def test_apply_requires_confirm(
    tmp_path: Path,
    capsys,
) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"

    source_root.mkdir()
    quarantine_root.mkdir()

    exit_code = cli.main(
        [
            "scan",
            "--source",
            str(source_root),
            "--quarantine",
            str(quarantine_root),
            "--report-dir",
            str(tmp_path / "reports"),
            "--apply",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "--apply requires --confirm" in captured.err


def test_apply_quarantines_only_move_candidates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"
    report_dir = tmp_path / "reports"

    source_root.mkdir()
    quarantine_root.mkdir()

    candidate = make_move_candidate(source_root)

    review_pair = CandidatePair(
        heic=ImageInfo(path=source_root / "2024" / "IMG_9999.HEIC"),
        jpg=ImageInfo(path=source_root / "2024" / "IMG_9999.JPG"),
    )

    review_evaluation = EvaluationResult(
        pair=review_pair,
        decision=Decision.REVIEW,
        reason_codes=(ReasonCode.DIMENSIONS_MISMATCH,),
    )

    monkeypatch.setattr(cli, "find_file_groups", lambda path: [])

    monkeypatch.setattr(
        cli,
        "evaluate_groups",
        lambda groups, config, hash_calculator=None: WorkflowResult(
            evaluations=(candidate, review_evaluation),
            ambiguous_groups=(),
        ),
    )

    def fake_write_evaluation_report(
        result: WorkflowResult,
        source_root: Path,
        output_path: Path,
    ) -> int:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.touch()
        return 2

    monkeypatch.setattr(
        cli,
        "write_evaluation_report",
        fake_write_evaluation_report,
    )

    quarantined_files: list[Path] = []

    def fake_quarantine_file(
        source_file: Path,
        source_root: Path,
        quarantine_root: Path,
    ) -> QuarantineResult:
        quarantined_files.append(source_file)

        return QuarantineResult(
            status=QuarantineStatus.MOVED,
            source_path=source_file,
            quarantine_path=quarantine_root / "2024" / source_file.name,
            message="Test move completed.",
            source_sha256="test-hash",
            quarantine_sha256="test-hash",
        )

    monkeypatch.setattr(
        cli,
        "quarantine_file",
        fake_quarantine_file,
    )

    action_logs: list[Path] = []

    def fake_write_action_log(
        results: object,
        source_root: Path,
        quarantine_root: Path,
        output_path: Path,
        *,
        timestamp: datetime | None = None,
    ) -> int:
        action_logs.append(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.touch()
        return 1

    monkeypatch.setattr(
        cli,
        "write_quarantine_action_log",
        fake_write_action_log,
    )

    exit_code = cli.main(
        [
            "scan",
            "--source",
            str(source_root),
            "--quarantine",
            str(quarantine_root),
            "--report-dir",
            str(report_dir),
            "--apply",
            "--confirm",
        ]
    )

    assert exit_code == 0
    assert quarantined_files == [candidate.pair.jpg.path]
    assert len(action_logs) == 1


def test_rejects_overlapping_source_and_quarantine_roots(
    tmp_path: Path,
    capsys,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()

    exit_code = cli.main(
        [
            "scan",
            "--source",
            str(source_root),
            "--quarantine",
            str(source_root / "quarantine"),
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "overlap" in captured.err
