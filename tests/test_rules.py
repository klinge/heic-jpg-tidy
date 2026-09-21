# tests/test_rules.py
from datetime import datetime, timedelta
from pathlib import Path

from heic_jpg_tidy.models import (
    CandidatePair,
    Decision,
    ImageInfo,
    ReasonCode,
    RuleConfig,
)
from heic_jpg_tidy.rules import evaluate_pair

BASE_TIME = datetime(2024, 7, 15, 12, 30, 0)


def make_pair(
    *,
    heic_datetime: datetime | None = BASE_TIME,
    jpg_datetime: datetime | None = BASE_TIME,
    heic_make: str | None = "Apple",
    jpg_make: str | None = "Apple",
    heic_model: str | None = "iPhone 15 Pro",
    jpg_model: str | None = "iPhone 15 Pro",
    heic_width: int | None = 4032,
    heic_height: int | None = 3024,
    jpg_width: int | None = 4032,
    jpg_height: int | None = 3024,
) -> CandidatePair:
    """Create a pair with safe default values for rule tests."""
    return CandidatePair(
        heic=ImageInfo(
            path=Path("photos/IMG_1234.HEIC"),
            datetime_original=heic_datetime,
            make=heic_make,
            model=heic_model,
            width=heic_width,
            height=heic_height,
        ),
        jpg=ImageInfo(
            path=Path("photos/IMG_1234.JPG"),
            datetime_original=jpg_datetime,
            make=jpg_make,
            model=jpg_model,
            width=jpg_width,
            height=jpg_height,
        ),
    )


def test_matching_pair_is_move_candidate() -> None:
    result = evaluate_pair(make_pair(), RuleConfig())

    assert result.decision is Decision.MOVE_CANDIDATE
    assert result.reason_codes == (ReasonCode.MATCH_CONFIRMED,)
    assert result.datetime_difference_seconds == 0
    assert result.dimensions_match is True


def test_datetime_within_tolerance_is_move_candidate() -> None:
    pair = make_pair(jpg_datetime=BASE_TIME + timedelta(seconds=5))

    result = evaluate_pair(
        pair,
        RuleConfig(datetime_tolerance_seconds=5),
    )

    assert result.decision is Decision.MOVE_CANDIDATE
    assert result.datetime_difference_seconds == 5


def test_datetime_outside_tolerance_requires_review() -> None:
    pair = make_pair(jpg_datetime=BASE_TIME + timedelta(seconds=6))

    result = evaluate_pair(
        pair,
        RuleConfig(datetime_tolerance_seconds=5),
    )

    assert result.decision is Decision.REVIEW
    assert result.reason_codes == (ReasonCode.DATETIME_MISMATCH,)


def test_missing_datetime_requires_review() -> None:
    result = evaluate_pair(
        make_pair(jpg_datetime=None),
        RuleConfig(),
    )

    assert result.decision is Decision.REVIEW
    assert result.reason_codes == (ReasonCode.DATETIME_MISSING,)


def test_different_camera_model_requires_review() -> None:
    result = evaluate_pair(
        make_pair(jpg_model="iPhone 14 Pro"),
        RuleConfig(),
    )

    assert result.decision is Decision.REVIEW
    assert result.reason_codes == (ReasonCode.CAMERA_MODEL_MISMATCH,)


def test_missing_camera_metadata_is_allowed() -> None:
    result = evaluate_pair(
        make_pair(jpg_make=None, jpg_model=None),
        RuleConfig(),
    )

    assert result.decision is Decision.MOVE_CANDIDATE
    assert result.make_match is None
    assert result.model_match is None


def test_different_dimensions_requires_review() -> None:
    result = evaluate_pair(
        make_pair(jpg_width=3000, jpg_height=2250),
        RuleConfig(),
    )

    assert result.decision is Decision.REVIEW
    assert result.reason_codes == (ReasonCode.DIMENSIONS_MISMATCH,)


def test_hash_verification_rejects_distant_images() -> None:
    result = evaluate_pair(
        make_pair(),
        RuleConfig(verify_image_hash=True, max_hash_distance=4),
        image_hash_distance=5,
    )

    assert result.decision is Decision.REVIEW
    assert result.reason_codes == (ReasonCode.IMAGE_HASH_MISMATCH,)


def test_hash_verification_accepts_matching_images() -> None:
    result = evaluate_pair(
        make_pair(),
        RuleConfig(verify_image_hash=True, max_hash_distance=4),
        image_hash_distance=2,
    )

    assert result.decision is Decision.MOVE_CANDIDATE
