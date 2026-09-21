"""Image metadata reading for HEIC, HEIF, JPG, and JPEG files."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image
from pillow_heif.as_plugin import register_heif_opener

from .models import ImageInfo

# Register HEIC/HEIF support with Pillow.
# This is safe to call once when the module is imported.
register_heif_opener()


# Standard EXIF tag IDs.
EXIF_MAKE = 271
EXIF_MODEL = 272
EXIF_ORIENTATION = 274
EXIF_DATETIME_ORIGINAL = 36867


# These orientation values represent a 90 or 270 degree rotation.
ROTATED_ORIENTATIONS = frozenset({5, 6, 7, 8})


def clean_exif_value(value: Any) -> str | None:
    """
    Convert an EXIF value to a clean string.

    EXIF values may be strings, bytes, numbers, or library-specific types.
    Empty values are normalized to None.
    """
    if value is None:
        return None

    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")

    cleaned = str(value).replace("\x00", "").strip()
    return cleaned or None


def parse_exif_datetime(value: Any) -> datetime | None:
    """
    Parse a DateTimeOriginal value into a datetime object.

    The standard EXIF format is:
        YYYY:MM:DD HH:MM:SS

    A few common alternatives are also accepted because exported files may
    use ISO-like formats instead.
    """
    cleaned = clean_exif_value(value)

    if cleaned is None:
        return None

    supported_formats = (
        "%Y:%m:%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    )

    for date_format in supported_formats:
        try:
            return datetime.strptime(cleaned, date_format)
        except ValueError:
            continue

    return None


def get_display_dimensions(
    width: int,
    height: int,
    orientation: Any,
) -> tuple[int, int]:
    """
    Return image dimensions after applying EXIF orientation.

    Camera files often store the raw sensor dimensions and use an EXIF
    orientation flag to indicate how the image should be displayed. For
    comparisons, the displayed dimensions are more useful than raw dimensions.
    """
    try:
        orientation_value = int(orientation) if orientation is not None else None
    except (TypeError, ValueError):
        orientation_value = None

    if orientation_value in ROTATED_ORIENTATIONS:
        return height, width

    return width, height


def read_image_info(path: Path) -> ImageInfo:
    """
    Read selected metadata and displayed dimensions from an image file.

    Errors are captured in ImageInfo.read_error so one unreadable or corrupt
    image does not terminate a complete archive scan.
    """
    try:
        with Image.open(path) as image:
            exif = image.getexif()

            raw_width, raw_height = image.size
            width, height = get_display_dimensions(
                raw_width,
                raw_height,
                exif.get(EXIF_ORIENTATION),
            )

            return ImageInfo(
                path=path,
                width=width,
                height=height,
                datetime_original=parse_exif_datetime(exif.get(EXIF_DATETIME_ORIGINAL)),
                make=clean_exif_value(exif.get(EXIF_MAKE)),
                model=clean_exif_value(exif.get(EXIF_MODEL)),
            )

    except Exception as error:
        return ImageInfo(
            path=path,
            read_error=f"{type(error).__name__}: {error}",
        )
