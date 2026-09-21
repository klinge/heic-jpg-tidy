"""Tests for safe quarantine operations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from heic_jpg_tidy.models import QuarantineStatus
from heic_jpg_tidy.quarantine import (
    calculate_sha256,
    get_quarantine_path,
    quarantine_file,
)


def create_file(path: Path, content: bytes = b"test content") -> Path:
    """Create a test file, including missing parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_calculate_sha256_is_consistent(tmp_path: Path) -> None:
    first_file = create_file(tmp_path / "first.jpg", b"same content")
    second_file = create_file(tmp_path / "second.jpg", b"same content")
    different_file = create_file(tmp_path / "different.jpg", b"different content")

    assert calculate_sha256(first_file) == calculate_sha256(second_file)
    assert calculate_sha256(first_file) != calculate_sha256(different_file)


def test_get_quarantine_path_preserves_relative_structure(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"

    source_file = source_root / "2024" / "Vacation" / "IMG_1234.JPG"

    destination = get_quarantine_path(
        source_file,
        source_root,
        quarantine_root,
    )

    assert destination == (quarantine_root / "2024" / "Vacation" / "IMG_1234.JPG")


def test_successful_quarantine_copies_verifies_and_removes_source(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"

    source_file = create_file(
        source_root / "2024" / "Vacation" / "IMG_1234.JPG",
        b"photo data",
    )

    result = quarantine_file(
        source_file,
        source_root,
        quarantine_root,
    )

    expected_destination = quarantine_root / "2024" / "Vacation" / "IMG_1234.JPG"

    assert result.status is QuarantineStatus.MOVED
    assert result.quarantine_path == expected_destination.resolve()
    assert result.source_sha256 is not None
    assert result.source_sha256 == result.quarantine_sha256

    assert not source_file.exists()
    assert expected_destination.exists()
    assert expected_destination.read_bytes() == b"photo data"


def test_missing_source_file_is_skipped(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"
    missing_file = source_root / "2024" / "IMG_1234.JPG"

    result = quarantine_file(
        missing_file,
        source_root,
        quarantine_root,
    )

    assert result.status is QuarantineStatus.SKIPPED
    assert "does not exist" in result.message
    assert not result.quarantine_path.exists()


def test_symbolic_link_is_skipped_without_following_target(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"
    target_file = create_file(source_root / "2024" / "IMG_1234.JPG")
    linked_file = source_root / "2024" / "IMG_1234-link.JPG"
    linked_file.symlink_to(target_file)

    result = quarantine_file(
        linked_file,
        source_root,
        quarantine_root,
    )

    assert result.status is QuarantineStatus.SKIPPED
    assert "symbolic link" in result.message
    assert linked_file.is_symlink()
    assert target_file.exists()


def test_existing_destination_is_not_overwritten(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"

    source_file = create_file(
        source_root / "2024" / "IMG_1234.JPG",
        b"source file",
    )

    destination_file = create_file(
        quarantine_root / "2024" / "IMG_1234.JPG",
        b"existing quarantine file",
    )

    result = quarantine_file(
        source_file,
        source_root,
        quarantine_root,
    )

    assert result.status is QuarantineStatus.SKIPPED
    assert "already exists" in result.message

    assert source_file.exists()
    assert source_file.read_bytes() == b"source file"

    assert destination_file.exists()
    assert destination_file.read_bytes() == b"existing quarantine file"


def test_source_file_outside_source_root_is_skipped(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"
    outside_file = create_file(tmp_path / "outside" / "IMG_1234.JPG")

    result = quarantine_file(
        outside_file,
        source_root,
        quarantine_root,
    )

    assert result.status is QuarantineStatus.SKIPPED
    assert "outside the configured source root" in result.message
    assert outside_file.exists()


def test_overlapping_source_and_quarantine_roots_are_skipped(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    quarantine_root = source_root / "quarantine"

    source_file = create_file(
        source_root / "2024" / "IMG_1234.JPG",
        b"photo data",
    )

    result = quarantine_file(
        source_file,
        source_root,
        quarantine_root,
    )

    assert result.status is QuarantineStatus.SKIPPED
    assert "overlap" in result.message
    assert source_file.exists()


def test_copy_failure_returns_error_and_keeps_source(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"

    source_file = create_file(
        source_root / "2024" / "IMG_1234.JPG",
        b"photo data",
    )

    def failing_copier(source: Path, destination: Path) -> None:
        raise OSError("Simulated copy failure")

    result = quarantine_file(
        source_file,
        source_root,
        quarantine_root,
        copier=failing_copier,
    )

    assert result.status is QuarantineStatus.ERROR
    assert "Simulated copy failure" in result.message
    assert source_file.exists()
    assert not result.quarantine_path.exists()


def test_hash_mismatch_returns_error_and_keeps_source(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"

    source_file = create_file(
        source_root / "2024" / "IMG_1234.JPG",
        b"photo data",
    )

    resolved_source = source_file.resolve()

    def mismatching_hasher(path: Path) -> str:
        if path.resolve() == resolved_source:
            return "source-hash"

        return "copied-file-hash"

    result = quarantine_file(
        source_file,
        source_root,
        quarantine_root,
        hasher=mismatching_hasher,
    )

    assert result.status is QuarantineStatus.ERROR
    assert "SHA-256 verification failed" in result.message

    assert source_file.exists()
    assert not result.quarantine_path.exists()

    temporary_files = list(quarantine_root.rglob("*.copying"))
    assert temporary_files == []


def test_unlink_failure_after_successful_copy_returns_error(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    quarantine_root = tmp_path / "quarantine"

    source_file = create_file(
        source_root / "2024" / "IMG_1234.JPG",
        b"photo data",
    )

    with patch.object(Path, "unlink", side_effect=OSError("Simulated unlink failure")):
        result = quarantine_file(
            source_file,
            source_root,
            quarantine_root,
        )

    assert result.status is QuarantineStatus.ERROR
    assert "could not be removed" in result.message
    assert result.source_sha256 is not None
    assert result.source_sha256 == result.quarantine_sha256
    assert result.quarantine_path.exists()
    assert result.quarantine_path.read_bytes() == b"photo data"
