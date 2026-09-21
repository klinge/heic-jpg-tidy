# src/heic_jpg_tidy/rules.py
"""Rules for evaluating possible HEIC/JPG duplicate pairs."""

from __future__ import annotations

from .models import (
    CandidatePair,
    Decision,
    EvaluationResult,
    ReasonCode,
    RuleConfig,
)


def normalize_camera_value(value: str | None) -> str | None:
    """Normalize camera metadata for comparison."""
    if value is None:
        return None

    normalized = " ".join(value.casefold().split())
    return normalized or None


def calculate_datetime_difference_seconds(pair: CandidatePair) -> float | None:
    """Return the absolute DateTimeOriginal difference in seconds."""
    heic_datetime = pair.heic.datetime_original
    jpg_datetime = pair.jpg.datetime_original

    if heic_datetime is None or jpg_datetime is None:
        return None

    return abs((heic_datetime - jpg_datetime).total_seconds())


def compare_camera_metadata(
    pair: CandidatePair,
) -> tuple[bool | None, bool | None]:
    """
    Compare Make and Model metadata.

    Returns:
        A tuple of (make_match, model_match).

        True: both values exist and match.
        False: both values exist and differ.
        None: one or both values are missing.
    """
    heic_make = normalize_camera_value(pair.heic.make)
    jpg_make = normalize_camera_value(pair.jpg.make)

    heic_model = normalize_camera_value(pair.heic.model)
    jpg_model = normalize_camera_value(pair.jpg.model)

    make_match: bool | None
    model_match: bool | None

    if heic_make is None or jpg_make is None:
        make_match = None
    else:
        make_match = heic_make == jpg_make

    if heic_model is None or jpg_model is None:
        model_match = None
    else:
        model_match = heic_model == jpg_model

    return make_match, model_match


def compare_dimensions(pair: CandidatePair) -> bool | None:
    """
    Compare displayed image dimensions.

    None means dimensions are unavailable for at least one file.
    """
    heic = pair.heic
    jpg = pair.jpg

    if None in {heic.width, heic.height, jpg.width, jpg.height}:
        return None

    return heic.width == jpg.width and heic.height == jpg.height


def evaluate_pair(
    pair: CandidatePair,
    config: RuleConfig,
    image_hash_distance: int | None = None,
    image_hash_error: str | None = None,
) -> EvaluationResult:
    """
    Evaluate whether a JPG is a safe quarantine candidate.

    A pair qualifies only when:
    - both files were read successfully;
    - DateTimeOriginal exists in both files and is within tolerance;
    - Make/Model do not conflict when both values exist;
    - dimensions exist and match exactly;
    - if hash verification is enabled, perceptual hash is within tolerance.
    """
    details: list[str] = []

    if pair.heic.read_error or pair.jpg.read_error:
        if pair.heic.read_error:
            details.append(f"Could not read HEIC: {pair.heic.read_error}")
        if pair.jpg.read_error:
            details.append(f"Could not read JPG: {pair.jpg.read_error}")

        return EvaluationResult(
            pair=pair,
            decision=Decision.REVIEW,
            reason_codes=(ReasonCode.IMAGE_READ_ERROR,),
            details=tuple(details),
        )

    datetime_difference = calculate_datetime_difference_seconds(pair)

    if datetime_difference is None:
        return EvaluationResult(
            pair=pair,
            decision=Decision.REVIEW,
            reason_codes=(ReasonCode.DATETIME_MISSING,),
            details=("DateTimeOriginal is missing from at least one file.",),
        )

    if datetime_difference > config.datetime_tolerance_seconds:
        return EvaluationResult(
            pair=pair,
            decision=Decision.REVIEW,
            reason_codes=(ReasonCode.DATETIME_MISMATCH,),
            details=(
                f"DateTimeOriginal differs by {datetime_difference:.3f} seconds; "
                f"allowed tolerance is {config.datetime_tolerance_seconds:.3f} seconds.",
            ),
            datetime_difference_seconds=datetime_difference,
        )

    make_match, model_match = compare_camera_metadata(pair)

    if make_match is False:
        return EvaluationResult(
            pair=pair,
            decision=Decision.REVIEW,
            reason_codes=(ReasonCode.CAMERA_MAKE_MISMATCH,),
            details=("Camera Make metadata differs between HEIC and JPG.",),
            datetime_difference_seconds=datetime_difference,
            make_match=make_match,
            model_match=model_match,
        )

    if model_match is False:
        return EvaluationResult(
            pair=pair,
            decision=Decision.REVIEW,
            reason_codes=(ReasonCode.CAMERA_MODEL_MISMATCH,),
            details=("Camera Model metadata differs between HEIC and JPG.",),
            datetime_difference_seconds=datetime_difference,
            make_match=make_match,
            model_match=model_match,
        )

    dimensions_match = compare_dimensions(pair)

    if dimensions_match is None:
        return EvaluationResult(
            pair=pair,
            decision=Decision.REVIEW,
            reason_codes=(ReasonCode.DIMENSIONS_MISSING,),
            details=("Image dimensions are missing for at least one file.",),
            datetime_difference_seconds=datetime_difference,
            make_match=make_match,
            model_match=model_match,
        )

    if dimensions_match is False:
        return EvaluationResult(
            pair=pair,
            decision=Decision.REVIEW,
            reason_codes=(ReasonCode.DIMENSIONS_MISMATCH,),
            details=("Image dimensions differ between HEIC and JPG.",),
            datetime_difference_seconds=datetime_difference,
            make_match=make_match,
            model_match=model_match,
            dimensions_match=dimensions_match,
        )

    if config.verify_image_hash:
        if image_hash_error is not None:
            return EvaluationResult(
                pair=pair,
                decision=Decision.REVIEW,
                reason_codes=(ReasonCode.IMAGE_HASH_ERROR,),
                details=(f"Could not calculate image hash: {image_hash_error}",),
                datetime_difference_seconds=datetime_difference,
                make_match=make_match,
                model_match=model_match,
                dimensions_match=dimensions_match,
            )

        if image_hash_distance is None:
            return EvaluationResult(
                pair=pair,
                decision=Decision.REVIEW,
                reason_codes=(ReasonCode.IMAGE_HASH_ERROR,),
                details=(
                    "Image hash verification was enabled but no result was provided.",
                ),
                datetime_difference_seconds=datetime_difference,
                make_match=make_match,
                model_match=model_match,
                dimensions_match=dimensions_match,
            )

        if image_hash_distance > config.max_hash_distance:
            return EvaluationResult(
                pair=pair,
                decision=Decision.REVIEW,
                reason_codes=(ReasonCode.IMAGE_HASH_MISMATCH,),
                details=(
                    f"Image hash distance is {image_hash_distance}; "
                    f"allowed maximum is {config.max_hash_distance}.",
                ),
                datetime_difference_seconds=datetime_difference,
                make_match=make_match,
                model_match=model_match,
                dimensions_match=dimensions_match,
                image_hash_distance=image_hash_distance,
            )

    return EvaluationResult(
        pair=pair,
        decision=Decision.MOVE_CANDIDATE,
        reason_codes=(ReasonCode.MATCH_CONFIRMED,),
        details=(
            "Filename pairing, DateTimeOriginal, camera metadata, and image "
            "dimensions satisfy the configured rules.",
        ),
        datetime_difference_seconds=datetime_difference,
        make_match=make_match,
        model_match=model_match,
        dimensions_match=dimensions_match,
        image_hash_distance=image_hash_distance,
    )
