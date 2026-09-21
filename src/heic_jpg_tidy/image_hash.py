"""Perceptual image hash calculation for HEIC/JPG verification."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


def calculate_phash_distance(
    first_path: Path,
    second_path: Path,
) -> tuple[int | None, str | None]:
    """
    Calculate perceptual hash distance between two image files.

    A lower distance means the images are more visually similar.

    Returns:
        A tuple containing:
        - the Hamming distance between image hashes, or None on failure;
        - an error message, or None on success.

    The function applies EXIF orientation before hashing and converts images
    to RGB to make comparison more consistent between HEIC and JPG files.
    """
    try:
        import imagehash
    except ImportError:
        return (
            None,
            "ImageHash is not installed. Install the optional hash dependency "
            "to enable image hash verification.",
        )

    try:
        with Image.open(first_path) as first_image:
            first_hash = imagehash.phash(_prepare_image_for_hash(first_image))

        with Image.open(second_path) as second_image:
            second_hash = imagehash.phash(_prepare_image_for_hash(second_image))

        return first_hash - second_hash, None

    except Exception as error:
        return None, f"{type(error).__name__}: {error}"


def _prepare_image_for_hash(image: Image.Image) -> Image.Image:
    """
    Apply display orientation and normalize an image before hashing.

    ImageHash itself resizes images internally, so this function does not need
    to resize full-resolution source images manually.
    """
    oriented_image = ImageOps.exif_transpose(image)
    return oriented_image.convert("RGB")
