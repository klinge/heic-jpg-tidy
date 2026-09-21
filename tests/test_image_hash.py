"""Tests for perceptual image hash calculation."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from heic_jpg_tidy.image_hash import (
    _prepare_image_for_hash,
    calculate_phash_distance,
)


def create_pattern_image(
    path: Path,
    *,
    inverted: bool = False,
) -> Path:
    """
    Create a visually distinctive test image.

    A simple solid-color image is not suitable for perceptual hash tests
    because different colors can sometimes produce identical hashes.
    """
    background = "white" if not inverted else "black"
    foreground = "black" if not inverted else "white"

    with Image.new("RGB", (320, 240), color=background) as image:
        draw = ImageDraw.Draw(image)

        draw.rectangle((20, 20, 150, 120), fill=foreground)
        draw.ellipse((180, 40, 290, 160), fill=foreground)
        draw.line((0, 239, 319, 0), fill=foreground, width=8)

        image.save(path, format="JPEG", quality=95)

    return path


def test_identical_images_have_zero_hash_distance(tmp_path: Path) -> None:
    first_path = create_pattern_image(tmp_path / "first.jpg")
    second_path = tmp_path / "second.jpg"

    # Use an exact file copy to ensure that both images are identical.
    second_path.write_bytes(first_path.read_bytes())

    distance, error = calculate_phash_distance(first_path, second_path)

    assert error is None
    assert distance == 0


def test_visually_different_images_have_nonzero_hash_distance(
    tmp_path: Path,
) -> None:
    first_path = create_pattern_image(tmp_path / "first.jpg")
    second_path = create_pattern_image(
        tmp_path / "second.jpg",
        inverted=True,
    )

    distance, error = calculate_phash_distance(first_path, second_path)

    assert error is None
    assert distance is not None
    assert distance > 0


def test_missing_file_returns_error(tmp_path: Path) -> None:
    existing_path = create_pattern_image(tmp_path / "existing.jpg")
    missing_path = tmp_path / "missing.jpg"

    distance, error = calculate_phash_distance(existing_path, missing_path)

    assert distance is None
    assert error is not None
    assert "FileNotFoundError" in error


def test_invalid_image_file_returns_error(tmp_path: Path) -> None:
    invalid_path = tmp_path / "not_an_image.jpg"
    invalid_path.write_text("This is not a valid image file.", encoding="utf-8")

    distance, error = calculate_phash_distance(invalid_path, invalid_path)

    assert distance is None
    assert error is not None


def test_prepare_image_applies_exif_orientation() -> None:
    with Image.new("RGB", (400, 300), color="white") as image:
        exif = image.getexif()
        exif[274] = 6  # Rotate 90 degrees clockwise.

        image.info["exif"] = exif.tobytes()

        prepared_image = _prepare_image_for_hash(image)

    assert prepared_image.mode == "RGB"
    assert prepared_image.size == (300, 400)
