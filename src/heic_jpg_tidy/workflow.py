"""Workflow orchestration for HEIC/JPG pair evaluation."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace
from pathlib import Path

from .metadata import read_image_info
from .models import (
    CandidatePair,
    Decision,
    FileGroup,
    ImageInfo,
    RuleConfig,
    WorkflowResult,
)
from .rules import evaluate_pair

# A hash calculator returns:
#
#   (distance, None)
#
# when successful, or:
#
#   (None, error_message)
#
# when hashing could not be completed.
HashCalculator = Callable[[Path, Path], tuple[int | None, str | None]]

# Metadata readers are injected to make workflow tests independent from
# Pillow, actual image files, and EXIF data.
MetadataReader = Callable[[Path], ImageInfo]


def evaluate_groups(
    groups: Iterable[FileGroup],
    config: RuleConfig,
    *,
    metadata_reader: MetadataReader = read_image_info,
    hash_calculator: HashCalculator | None = None,
) -> WorkflowResult:
    """
    Evaluate discovered HEIC/JPG file groups.

    Unambiguous groups, containing exactly one HEIC/HEIF and one JPG/JPEG,
    are read and evaluated using the configured rules.

    Ambiguous groups are preserved separately for later reporting. They are
    never automatically considered move candidates.

    When image hash verification is enabled, hashing is performed only after
    all metadata-based rules have already produced a MOVE_CANDIDATE result.
    This avoids unnecessary image decoding for pairs that already require
    manual review.
    """
    if config.verify_image_hash and hash_calculator is None:
        raise ValueError(
            "Hash verification is enabled, but no hash calculator was provided."
        )

    evaluations = []
    ambiguous_groups = []

    # This configuration is used for the initial metadata-only evaluation.
    # It lets us avoid calculating hashes for pairs that already fail a
    # required metadata rule.
    metadata_only_config = replace(config, verify_image_hash=False)

    for group in groups:
        if not group.is_unambiguous_pair:
            ambiguous_groups.append(group)
            continue

        pair = create_candidate_pair(group, metadata_reader)

        preliminary_result = evaluate_pair(pair, metadata_only_config)

        # Hash verification is disabled, or the pair already failed another
        # rule. In both cases, the preliminary result is the final result.
        if (
            not config.verify_image_hash
            or preliminary_result.decision is not Decision.MOVE_CANDIDATE
        ):
            evaluations.append(preliminary_result)
            continue

        # At this point the pair passed all metadata checks. Hashing is now
        # used as an additional safety check.
        hash_distance, hash_error = calculate_hash_safely(
            pair,
            hash_calculator,
        )

        final_result = evaluate_pair(
            pair,
            config,
            image_hash_distance=hash_distance,
            image_hash_error=hash_error,
        )
        evaluations.append(final_result)

    return WorkflowResult(
        evaluations=tuple(evaluations),
        ambiguous_groups=tuple(ambiguous_groups),
    )


def create_candidate_pair(
    group: FileGroup,
    metadata_reader: MetadataReader,
) -> CandidatePair:
    """
    Read metadata for an unambiguous FileGroup and create a CandidatePair.

    Raises:
        ValueError: If the supplied group does not contain exactly one HEIC
            and exactly one JPG file.
    """
    if not group.is_unambiguous_pair:
        raise ValueError("Cannot create a CandidatePair from an ambiguous file group.")

    heic_path = group.heic_paths[0]
    jpg_path = group.jpg_paths[0]

    return CandidatePair(
        heic=read_metadata_safely(heic_path, metadata_reader),
        jpg=read_metadata_safely(jpg_path, metadata_reader),
    )


def read_metadata_safely(
    path: Path,
    metadata_reader: MetadataReader,
) -> ImageInfo:
    """
    Read image metadata without allowing one unexpected exception to abort a scan.

    The normal metadata reader already catches image-related errors. This
    additional guard protects the workflow against unexpected implementation
    errors and custom/injected metadata readers.
    """
    try:
        return metadata_reader(path)
    except Exception as error:
        return ImageInfo(
            path=path,
            read_error=f"{type(error).__name__}: {error}",
        )


def calculate_hash_safely(
    pair: CandidatePair,
    hash_calculator: HashCalculator | None,
) -> tuple[int | None, str | None]:
    """
    Calculate perceptual hash distance without aborting the complete workflow.
    """
    if hash_calculator is None:
        return None, "No hash calculator was provided."

    try:
        return hash_calculator(pair.heic.path, pair.jpg.path)
    except Exception as error:
        return None, f"{type(error).__name__}: {error}"
