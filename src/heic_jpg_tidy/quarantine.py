"""Safe quarantine operations for confirmed JPG move candidates."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from collections.abc import Callable
from pathlib import Path

from .models import QuarantineResult, QuarantineStatus

FileHasher = Callable[[Path], str]
FileCopier = Callable[[Path, Path], object]


def calculate_sha256(path: Path, block_size: int = 1024 * 1024) -> str:
    """
    Calculate a SHA-256 checksum without loading the full file into memory.
    """
    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        while True:
            block = file_handle.read(block_size)

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


def is_inside_directory(path: Path, directory: Path) -> bool:
    """Return True when path is located inside directory."""
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def paths_overlap(first: Path, second: Path) -> bool:
    """
    Return True when either directory contains the other.

    A quarantine directory must not be the source directory, a child of it,
    or a parent of it. Allowing overlap could cause confusing or unsafe
    destination paths.
    """
    return is_inside_directory(first, second) or is_inside_directory(second, first)


def get_quarantine_path(
    source_file: Path,
    source_root: Path,
    quarantine_root: Path,
) -> Path:
    """
    Return the quarantine destination while preserving relative structure.

    Example:
        source_file:
            D:/PhotoArchive/2024/Trip/IMG_1234.JPG

        source_root:
            D:/PhotoArchive

        quarantine_root:
            E:/PhotoArchive_Quarantine

        result:
            E:/PhotoArchive_Quarantine/2024/Trip/IMG_1234.JPG
    """
    relative_path = source_file.relative_to(source_root)
    return quarantine_root / relative_path


def create_temporary_destination(destination_path: Path) -> Path:
    """
    Create a unique temporary path in the destination directory.

    The temporary file is deliberately created in the same directory as the
    final destination. This allows os.replace() to be atomic on a normal
    local filesystem once copying and verification have completed.
    """
    temporary_name = f".{destination_path.name}.{uuid.uuid4().hex}.copying"

    return destination_path.with_name(temporary_name)


def quarantine_file(
    source_file: Path,
    source_root: Path,
    quarantine_root: Path,
    *,
    hasher: FileHasher = calculate_sha256,
    copier: FileCopier = shutil.copy2,
) -> QuarantineResult:
    """
    Copy, verify, and remove one source file safely.

    The source file is removed only after all of the following steps succeed:

    1. Copy source to a temporary file in the quarantine destination directory.
    2. Verify that source and temporary copy have equal file size.
    3. Verify that source and temporary copy have identical SHA-256 hashes.
    4. Atomically rename the temporary file to its final destination.
    5. Remove the original source file.

    Existing destination files are never overwritten.

    Returns:
        A QuarantineResult. Expected safety conditions produce SKIPPED.
        Unexpected filesystem, copy, or verification failures produce ERROR.
    """
    source_file = source_file.resolve()
    source_root = source_root.resolve()
    quarantine_root = quarantine_root.resolve()

    # The final path is calculated early so every result can include it where
    # possible, including skipped operations.
    try:
        destination_path = get_quarantine_path(
            source_file,
            source_root,
            quarantine_root,
        )
    except ValueError:
        destination_path = quarantine_root / source_file.name

        return QuarantineResult(
            status=QuarantineStatus.SKIPPED,
            source_path=source_file,
            quarantine_path=destination_path,
            message=(
                "Source file is outside the configured source root. "
                "No action was performed."
            ),
        )

    if paths_overlap(source_root, quarantine_root):
        return QuarantineResult(
            status=QuarantineStatus.SKIPPED,
            source_path=source_file,
            quarantine_path=destination_path,
            message=(
                "Source root and quarantine root overlap. "
                "The quarantine root must be completely separate from "
                "the source root."
            ),
        )

    if not source_file.exists():
        return QuarantineResult(
            status=QuarantineStatus.SKIPPED,
            source_path=source_file,
            quarantine_path=destination_path,
            message="Source file does not exist. No action was performed.",
        )

    if source_file.is_symlink():
        return QuarantineResult(
            status=QuarantineStatus.SKIPPED,
            source_path=source_file,
            quarantine_path=destination_path,
            message=(
                "Source file is a symbolic link. Symbolic links are not "
                "quarantined automatically."
            ),
        )

    if not source_file.is_file():
        return QuarantineResult(
            status=QuarantineStatus.SKIPPED,
            source_path=source_file,
            quarantine_path=destination_path,
            message="Source path is not a regular file. No action was performed.",
        )

    if destination_path.exists():
        return QuarantineResult(
            status=QuarantineStatus.SKIPPED,
            source_path=source_file,
            quarantine_path=destination_path,
            message=(
                "Quarantine destination already exists. Existing files are "
                "never overwritten."
            ),
        )

    temporary_path: Path | None = None
    source_sha256: str | None = None
    quarantine_sha256: str | None = None
    destination_created = False

    try:
        destination_path.parent.mkdir(parents=True, exist_ok=True)

        temporary_path = create_temporary_destination(destination_path)

        if temporary_path.exists():
            raise FileExistsError(
                f"Temporary quarantine file already exists: {temporary_path}"
            )

        source_sha256 = hasher(source_file)

        copier(source_file, temporary_path)

        if not temporary_path.exists():
            raise OSError("Copy operation completed without creating a temporary file.")

        source_size = source_file.stat().st_size
        temporary_size = temporary_path.stat().st_size

        if source_size != temporary_size:
            raise OSError(
                "Copied file size does not match source file size: "
                f"source={source_size}, copy={temporary_size}."
            )

        quarantine_sha256 = hasher(temporary_path)

        if source_sha256 != quarantine_sha256:
            raise OSError("SHA-256 verification failed. Source and copied file differ.")

        # The temporary file and final file are in the same directory.
        # os.replace therefore acts as an atomic rename on normal filesystems.
        os.replace(temporary_path, destination_path)
        temporary_path = None
        destination_created = True

        source_file.unlink()

        return QuarantineResult(
            status=QuarantineStatus.MOVED,
            source_path=source_file,
            quarantine_path=destination_path,
            message=(
                "File copied to quarantine, verified with SHA-256, and "
                "removed from the source archive."
            ),
            source_sha256=source_sha256,
            quarantine_sha256=quarantine_sha256,
        )

    except Exception as error:
        # If the final destination was successfully created but deleting the
        # source failed, retain both copies. This is safer than deleting a
        # verified quarantine copy during error handling.
        if temporary_path is not None and temporary_path.exists():
            try:
                temporary_path.unlink()
            except OSError:
                pass

        if destination_created:
            message = (
                "Quarantine copy was created and verified, but the source "
                f"file could not be removed: {type(error).__name__}: {error}"
            )
        else:
            message = f"Quarantine operation failed: {type(error).__name__}: {error}"

        return QuarantineResult(
            status=QuarantineStatus.ERROR,
            source_path=source_file,
            quarantine_path=destination_path,
            message=message,
            source_sha256=source_sha256,
            quarantine_sha256=quarantine_sha256,
        )
