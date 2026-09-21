"""Tests for workflow orchestration."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from heic_jpg_tidy.models import (
    Decision,
    FileGroup,
    ImageInfo,
    RuleConfig,
)
from heic_jpg_tidy.workflow import (
    create_candidate_pair,
    evaluate_groups,
)

BASE_TIME = datetime(2024, 7, 15, 12, 30, 0)


def make_group(
    *,
    heic_paths: tuple[Path, ...] = (Path("photos/IMG_1234.HEIC"),),
    jpg_paths: tuple[Path, ...] = (Path("photos/IMG_1234.JPG"),),
) -> FileGroup:
    """Create a file group for workflow tests."""
    return FileGroup(
        directory=Path("photos"),
        stem="img_1234",
        heic_paths=heic_paths,
        jpg_paths=jpg_paths,
    )


def fake_metadata_reader(path: Path) -> ImageInfo:
    """Return predictable metadata without opening an actual image file."""
    return ImageInfo(
        path=path,
        width=4032,
        height=3024,
        datetime_original=BASE_TIME,
        make="Apple",
        model="iPhone 15 Pro",
    )


def test_evaluates_unambiguous_group() -> None:
    result = evaluate_groups(
        [make_group()],
        RuleConfig(),
        metadata_reader=fake_metadata_reader,
    )

    assert len(result.evaluations) == 1
    assert result.ambiguous_groups == ()
    assert result.evaluations[0].decision is Decision.MOVE_CANDIDATE


def test_preserves_ambiguous_group_without_metadata_reads() -> None:
    group = make_group(
        jpg_paths=(
            Path("photos/IMG_1234.JPG"),
            Path("photos/IMG_1234.JPEG"),
        ),
    )

    def failing_metadata_reader(path: Path) -> ImageInfo:
        raise AssertionError("Metadata should not be read for ambiguous groups.")

    result = evaluate_groups(
        [group],
        RuleConfig(),
        metadata_reader=failing_metadata_reader,
    )

    assert result.evaluations == ()
    assert result.ambiguous_groups == (group,)


def test_hash_is_not_calculated_when_metadata_rules_fail() -> None:
    def mismatching_metadata_reader(path: Path) -> ImageInfo:
        width = 4032 if path.suffix.casefold() == ".heic" else 3000

        return ImageInfo(
            path=path,
            width=width,
            height=3024,
            datetime_original=BASE_TIME,
            make="Apple",
            model="iPhone 15 Pro",
        )

    def failing_hash_calculator(
        first_path: Path,
        second_path: Path,
    ) -> tuple[int | None, str | None]:
        raise AssertionError("Hash should not be calculated.")

    result = evaluate_groups(
        [make_group()],
        RuleConfig(verify_image_hash=True),
        metadata_reader=mismatching_metadata_reader,
        hash_calculator=failing_hash_calculator,
    )

    assert len(result.evaluations) == 1
    assert result.evaluations[0].decision is Decision.REVIEW


def test_hash_is_calculated_after_metadata_rules_pass() -> None:
    calls = 0

    def hash_calculator(
        first_path: Path,
        second_path: Path,
    ) -> tuple[int | None, str | None]:
        nonlocal calls
        calls += 1
        return 0, None

    result = evaluate_groups(
        [make_group()],
        RuleConfig(verify_image_hash=True, max_hash_distance=4),
        metadata_reader=fake_metadata_reader,
        hash_calculator=hash_calculator,
    )

    assert calls == 1
    assert len(result.evaluations) == 1
    assert result.evaluations[0].decision is Decision.MOVE_CANDIDATE
    assert result.evaluations[0].image_hash_distance == 0


def test_hash_mismatch_requires_review() -> None:
    result = evaluate_groups(
        [make_group()],
        RuleConfig(verify_image_hash=True, max_hash_distance=4),
        metadata_reader=fake_metadata_reader,
        hash_calculator=lambda first_path, second_path: (5, None),
    )

    assert len(result.evaluations) == 1
    assert result.evaluations[0].decision is Decision.REVIEW


def test_hash_error_requires_review() -> None:
    result = evaluate_groups(
        [make_group()],
        RuleConfig(verify_image_hash=True),
        metadata_reader=fake_metadata_reader,
        hash_calculator=lambda first_path, second_path: (
            None,
            "Unable to decode HEIC image.",
        ),
    )

    assert len(result.evaluations) == 1
    assert result.evaluations[0].decision is Decision.REVIEW


def test_hash_configuration_requires_hash_calculator() -> None:
    with pytest.raises(ValueError, match="no hash calculator"):
        evaluate_groups(
            [make_group()],
            RuleConfig(verify_image_hash=True),
            metadata_reader=fake_metadata_reader,
        )


def test_create_candidate_pair_rejects_ambiguous_group() -> None:
    ambiguous_group = make_group(
        jpg_paths=(
            Path("photos/IMG_1234.JPG"),
            Path("photos/IMG_1234.JPEG"),
        ),
    )

    with pytest.raises(ValueError, match="ambiguous"):
        create_candidate_pair(
            ambiguous_group,
            fake_metadata_reader,
        )
