"""End-to-end integration tests for file discovery and evaluation."""

from __future__ import annotations

import shutil
from pathlib import Path

from heic_jpg_tidy import cli
from heic_jpg_tidy.models import Decision, ReasonCode, RuleConfig
from heic_jpg_tidy.scanner import find_file_groups
from heic_jpg_tidy.workflow import evaluate_groups

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures/generated"


def copy_fixture_directory(
    fixture_name: str,
    destination: Path,
) -> Path:
    """Copy a fixture directory to a temporary archive root."""
    source = FIXTURES_DIR / fixture_name
    target = destination / fixture_name
    shutil.copytree(source, target)
    return target


def test_real_matching_pair_becomes_move_candidate(tmp_path: Path) -> None:
    archive_root = copy_fixture_directory("matching_pair", tmp_path)

    groups = find_file_groups(archive_root)
    result = evaluate_groups(groups, RuleConfig())

    assert len(result.ambiguous_groups) == 0
    assert len(result.evaluations) == 1

    evaluation = result.evaluations[0]

    assert evaluation.decision is Decision.MOVE_CANDIDATE
    assert evaluation.reason_codes == (ReasonCode.MATCH_CONFIRMED,)


def test_real_ambiguous_group_requires_review(tmp_path: Path) -> None:
    archive_root = copy_fixture_directory("ambiguous_group", tmp_path)

    groups = find_file_groups(archive_root)
    result = evaluate_groups(groups, RuleConfig())

    assert result.evaluations == ()
    assert len(result.ambiguous_groups) == 1

    group = result.ambiguous_groups[0]

    assert len(group.heic_paths) == 1
    assert len(group.jpg_paths) == 2
    assert group.is_unambiguous_pair is False


def test_cli_dry_run_writes_evaluation_report(tmp_path: Path) -> None:
    archive_root = copy_fixture_directory("matching_pair", tmp_path)
    quarantine_root = tmp_path / "quarantine"
    report_dir = tmp_path / "reports"

    exit_code = cli.main(
        [
            "scan",
            "--source",
            str(archive_root),
            "--quarantine",
            str(quarantine_root),
            "--report-dir",
            str(report_dir),
        ]
    )

    assert exit_code == 0
    assert list(report_dir.glob("evaluation_*.csv"))
    assert not quarantine_root.exists()


def test_cli_apply_moves_only_confirmed_jpg(tmp_path: Path) -> None:
    archive_root = copy_fixture_directory("matching_pair", tmp_path)
    quarantine_root = tmp_path / "quarantine"
    report_dir = tmp_path / "reports"

    jpg_path = archive_root / "IMG_0001.JPG"
    heic_path = archive_root / "IMG_0001.HEIC"

    exit_code = cli.main(
        [
            "scan",
            "--source",
            str(archive_root),
            "--quarantine",
            str(quarantine_root),
            "--report-dir",
            str(report_dir),
            "--apply",
            "--confirm",
        ]
    )

    assert exit_code == 0
    assert heic_path.exists()
    assert not jpg_path.exists()
    assert (quarantine_root / "IMG_0001.JPG").exists()
    assert list(report_dir.glob("evaluation_*.csv"))
    assert list(report_dir.glob("quarantine_actions_*.csv"))
