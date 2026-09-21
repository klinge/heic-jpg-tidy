"""Generate synthetic HEIC/JPG test fixtures.

The generated files are intentionally synthetic and contain predictable EXIF
metadata. They are suitable for integration tests and must not contain private
photographs or personal metadata.
"""

from __future__ import annotations

import shutil
from contextlib import contextmanager
from collections.abc import Generator
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw
from pillow_heif.as_plugin import register_heif_opener

from heic_jpg_tidy.metadata import (
    EXIF_DATETIME_ORIGINAL,
    EXIF_MAKE,
    EXIF_MODEL,
    EXIF_ORIENTATION,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "generated"


register_heif_opener()


@contextmanager
def create_pattern_image(
    *,
    width: int = 640,
    height: int = 480,
    inverted: bool = False,
) -> Generator[Image.Image, None, None]:
    """
    Create a distinctive synthetic RGB image as a context manager.

    The image contains multiple shapes and colors so perceptual hash tests
    have meaningful visual data to compare.
    """
    background = (245, 245, 245) if not inverted else (20, 20, 20)
    foreground = (30, 30, 30) if not inverted else (230, 230, 230)

    image = Image.new("RGB", (width, height), background)
    try:
        draw = ImageDraw.Draw(image)

        # Top-left red rectangle.
        draw.rectangle(
            (30, 30, width // 3, height // 3),
            fill=(210, 60, 60),
            outline=foreground,
            width=5,
        )

        # Top-right blue ellipse.
        draw.ellipse(
            (width // 2, 40, width - 50, height // 2),
            fill=(65, 125, 210),
            outline=foreground,
            width=5,
        )

        # Bottom green triangle.
        draw.polygon(
            [
                (width // 2, height - 40),
                (width // 3, height // 2 + 40),
                (width - width // 4, height // 2 + 50),
            ],
            fill=(70, 170, 105),
            outline=foreground,
        )

        # Diagonal and horizontal lines make the image less symmetric.
        draw.line(
            (0, height - 1, width - 1, 0),
            fill=foreground,
            width=9,
        )
        draw.line(
            (20, height - 70, width - 20, height - 70),
            fill=(230, 175, 50),
            width=8,
        )

        yield image
    finally:
        image.close()


def create_exif(
    *,
    datetime_original: datetime | None,
    make: str | None = "Synthetic Camera Corp.",
    model: str | None = "FixtureCam 1",
    orientation: int | None = 1,
) -> bytes:
    """Create EXIF bytes suitable for JPG and HEIC fixture files."""
    exif = Image.Exif()

    if make is not None:
        exif[EXIF_MAKE] = make

    if model is not None:
        exif[EXIF_MODEL] = model

    if orientation is not None:
        exif[EXIF_ORIENTATION] = orientation

    if datetime_original is not None:
        exif[EXIF_DATETIME_ORIGINAL] = datetime_original.strftime("%Y:%m:%d %H:%M:%S")

    return exif.tobytes()


def save_jpg(
    image: Image.Image,
    path: Path,
    *,
    exif: bytes,
) -> None:
    """Save a synthetic JPEG fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)

    image.save(
        path,
        format="JPEG",
        quality=95,
        subsampling=0,
        exif=exif,
    )


def save_heic(
    image: Image.Image,
    path: Path,
    *,
    exif: bytes,
) -> None:
    """Save a synthetic HEIC fixture through pillow-heif's Pillow plugin."""
    path.parent.mkdir(parents=True, exist_ok=True)

    image.save(
        path,
        format="HEIF",
        quality=90,
        exif=exif,
    )


def write_matching_pair(output_dir: Path) -> None:
    """Create one expected MOVE_CANDIDATE HEIC/JPG pair."""
    timestamp = datetime(2025, 1, 15, 12, 30, 0)
    exif = create_exif(datetime_original=timestamp)

    with create_pattern_image() as image:
        save_heic(image, output_dir / "IMG_0001.HEIC", exif=exif)
        save_jpg(image, output_dir / "IMG_0001.JPG", exif=exif)


def write_dimensions_mismatch_pair(output_dir: Path) -> None:
    """Create a pair with deliberately different displayed dimensions."""
    timestamp = datetime(2025, 1, 15, 12, 31, 0)
    exif = create_exif(datetime_original=timestamp)

    with create_pattern_image(width=640, height=480) as image:
        save_heic(image, output_dir / "IMG_0002.HEIC", exif=exif)

    with create_pattern_image(width=600, height=450) as image:
        save_jpg(image, output_dir / "IMG_0002.JPG", exif=exif)


def write_datetime_mismatch_pair(output_dir: Path) -> None:
    """Create a pair whose DateTimeOriginal values differ by ten seconds."""
    heic_time = datetime(2025, 1, 15, 12, 32, 0)
    jpg_time = heic_time + timedelta(seconds=10)

    with create_pattern_image() as image:
        save_heic(image, output_dir / "IMG_0003.HEIC", exif=create_exif(datetime_original=heic_time))
        save_jpg(image, output_dir / "IMG_0003.JPG", exif=create_exif(datetime_original=jpg_time))


def write_missing_datetime_pair(output_dir: Path) -> None:
    """Create a pair where DateTimeOriginal is absent."""
    exif = create_exif(
        datetime_original=None,
        make="Synthetic Camera Corp.",
        model="FixtureCam 1",
    )

    with create_pattern_image() as image:
        save_heic(image, output_dir / "IMG_0004.HEIC", exif=exif)
        save_jpg(image, output_dir / "IMG_0004.JPG", exif=exif)


def write_camera_model_mismatch_pair(output_dir: Path) -> None:
    """Create a pair with conflicting camera model metadata."""
    timestamp = datetime(2025, 1, 15, 12, 34, 0)

    with create_pattern_image() as image:
        save_heic(image, output_dir / "IMG_0005.HEIC", exif=create_exif(datetime_original=timestamp, model="FixtureCam 1"))
        save_jpg(image, output_dir / "IMG_0005.JPG", exif=create_exif(datetime_original=timestamp, model="FixtureCam 2"))


def write_ambiguous_group(output_dir: Path) -> None:
    """Create one HEIC and two JPG-family files with the same stem."""
    timestamp = datetime(2025, 1, 15, 12, 35, 0)
    exif = create_exif(datetime_original=timestamp)

    with create_pattern_image() as image:
        save_heic(image, output_dir / "IMG_0006.HEIC", exif=exif)
        save_jpg(image, output_dir / "IMG_0006.JPG", exif=exif)
        save_jpg(image, output_dir / "IMG_0006.JPEG", exif=exif)


def write_corrupt_pair(output_dir: Path) -> None:
    """Create an otherwise valid group with an invalid JPG file."""
    timestamp = datetime(2025, 1, 15, 12, 36, 0)
    exif = create_exif(datetime_original=timestamp)

    with create_pattern_image() as image:
        save_heic(image, output_dir / "IMG_0007.HEIC", exif=exif)

    corrupt_jpg = output_dir / "IMG_0007.JPG"
    corrupt_jpg.parent.mkdir(parents=True, exist_ok=True)
    corrupt_jpg.write_text(
        "This is intentionally not a valid JPEG image.",
        encoding="utf-8",
    )


def write_hash_mismatch_pair(output_dir: Path) -> None:
    """Create a metadata-compatible pair with visibly different image content."""
    timestamp = datetime(2025, 1, 15, 12, 37, 0)
    exif = create_exif(datetime_original=timestamp)

    with create_pattern_image(inverted=False) as image:
        save_heic(image, output_dir / "IMG_0008.HEIC", exif=exif)

    with create_pattern_image(inverted=True) as image:
        save_jpg(image, output_dir / "IMG_0008.JPG", exif=exif)


def verify_generated_fixtures() -> None:
    """
    Verify that generated HEIC files can be read by the project's metadata code.

    This catches cases where pillow-heif can save a HEIF file but EXIF metadata
    was not retained as expected by the installed encoder/backend.
    """
    from heic_jpg_tidy.metadata import read_image_info

    expected_datetime_fixtures = (
        "matching_pair/IMG_0001.HEIC",
        "dimensions_mismatch/IMG_0002.HEIC",
        "datetime_mismatch/IMG_0003.HEIC",
        "camera_model_mismatch/IMG_0005.HEIC",
        "ambiguous_group/IMG_0006.HEIC",
        "corrupt_pair/IMG_0007.HEIC",
        "hash_mismatch/IMG_0008.HEIC",
    )

    for relative_path in expected_datetime_fixtures:
        path = OUTPUT_ROOT / relative_path
        info = read_image_info(path)

        if info.read_error is not None:
            raise RuntimeError(
                f"Generated HEIC fixture could not be read: {path}\n"
                f"Error: {info.read_error}"
            )

        if info.datetime_original is None:
            raise RuntimeError(
                f"Generated HEIC fixture is missing DateTimeOriginal: {path}\n"
                "Your installed HEIF encoder may not preserve EXIF metadata."
            )

    missing_datetime_path = OUTPUT_ROOT / "missing_datetime" / "IMG_0004.HEIC"
    missing_datetime_info = read_image_info(missing_datetime_path)

    if missing_datetime_info.read_error is not None:
        raise RuntimeError(
            f"Generated HEIC fixture could not be read: "
            f"{missing_datetime_path}\n"
            f"Error: {missing_datetime_info.read_error}"
        )

    if missing_datetime_info.datetime_original is not None:
        raise RuntimeError(
            "The missing_datetime fixture unexpectedly contains "
            "DateTimeOriginal metadata."
        )


def main() -> None:
    """Regenerate the complete synthetic fixture library."""
    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)

    write_matching_pair(OUTPUT_ROOT / "matching_pair")
    write_dimensions_mismatch_pair(OUTPUT_ROOT / "dimensions_mismatch")
    write_datetime_mismatch_pair(OUTPUT_ROOT / "datetime_mismatch")
    write_missing_datetime_pair(OUTPUT_ROOT / "missing_datetime")
    write_camera_model_mismatch_pair(OUTPUT_ROOT / "camera_model_mismatch")
    write_ambiguous_group(OUTPUT_ROOT / "ambiguous_group")
    write_corrupt_pair(OUTPUT_ROOT / "corrupt_pair")
    write_hash_mismatch_pair(OUTPUT_ROOT / "hash_mismatch")

    verify_generated_fixtures()

    print(f"Generated synthetic fixtures in: {OUTPUT_ROOT}")


if __name__ == "__main__":
    main()
