# src/heic_jpg_tidy/scanner.py
"""File discovery and grouping for HEIC/JPG candidate pairs."""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from .models import FileGroup

HEIC_EXTENSIONS = frozenset({".heic", ".heif"})
JPG_EXTENSIONS = frozenset({".jpg", ".jpeg"})
SUPPORTED_EXTENSIONS = HEIC_EXTENSIONS | JPG_EXTENSIONS


def normalize_stem(stem: str) -> str:
    """
    Normalize a filename stem for case-insensitive matching.

    Examples:
        IMG_1234 -> img_1234
        img_1234 -> img_1234
    """
    return stem.casefold()


def is_supported_image(path: Path) -> bool:
    """Return True when a path has a supported HEIC or JPG extension."""
    return path.suffix.casefold() in SUPPORTED_EXTENSIONS


def is_heic_file(path: Path) -> bool:
    """Return True when a path has a supported HEIC or HEIF extension."""
    return path.suffix.casefold() in HEIC_EXTENSIONS


def is_jpg_file(path: Path) -> bool:
    """Return True when a path has a supported JPG or JPEG extension."""
    return path.suffix.casefold() in JPG_EXTENSIONS


def find_file_groups(source: Path) -> list[FileGroup]:
    """
    Recursively find HEIC/JPG groups below a source directory.

    Files are grouped by normalized filename stem and parent directory.
    Only groups containing at least one HEIC/HEIF and at least one JPG/JPEG
    are returned.

    The returned list and each file list are sorted for deterministic output.
    """
    if not source.is_dir():
        raise NotADirectoryError(f"Source directory does not exist: {source}")

    resolved_source = source.resolve()
    grouped_paths: dict[tuple[Path, str], list[Path]] = defaultdict(list)

    for root, _, filenames in os.walk(resolved_source):
        directory = Path(root)

        for filename in filenames:
            path = directory.joinpath(filename).resolve()

            if not path.is_relative_to(resolved_source):
                continue

            if not is_supported_image(path):
                continue

            key = (directory, normalize_stem(path.stem))
            grouped_paths[key].append(path)

    file_groups: list[FileGroup] = []

    for (directory, stem), paths in grouped_paths.items():
        heic_paths = tuple(sorted(path for path in paths if is_heic_file(path)))
        jpg_paths = tuple(sorted(path for path in paths if is_jpg_file(path)))

        # This scanner is intentionally interested only in potentially
        # relevant groups. HEIC-only and JPG-only groups are ignored.
        if not heic_paths or not jpg_paths:
            continue

        file_groups.append(
            FileGroup(
                directory=directory,
                stem=stem,
                heic_paths=heic_paths,
                jpg_paths=jpg_paths,
            )
        )

    return sorted(
        file_groups,
        key=lambda group: (
            str(group.directory).casefold(),
            group.stem,
        ),
    )


def iter_unambiguous_groups(groups: Iterable[FileGroup]) -> Iterable[FileGroup]:
    """Yield only groups containing exactly one HEIC and one JPG."""
    return (group for group in groups if group.is_unambiguous_pair)
