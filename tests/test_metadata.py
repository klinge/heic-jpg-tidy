"""Tests for metadata parsing and normalization."""

from datetime import datetime

from heic_jpg_tidy.metadata import (
    clean_exif_value,
    get_display_dimensions,
    parse_exif_datetime,
)


def test_clean_exif_value_returns_none_for_empty_values() -> None:
    assert clean_exif_value(None) is None
    assert clean_exif_value("") is None
    assert clean_exif_value("   ") is None
    assert clean_exif_value(b"\x00") is None


def test_clean_exif_value_decodes_and_strips_bytes() -> None:
    assert clean_exif_value(b" Apple\x00 ") == "Apple"


def test_clean_exif_value_strips_text() -> None:
    assert clean_exif_value("  iPhone 15 Pro  ") == "iPhone 15 Pro"


def test_parse_standard_exif_datetime() -> None:
    result = parse_exif_datetime("2024:07:15 12:30:45")

    assert result == datetime(2024, 7, 15, 12, 30, 45)


def test_parse_exif_datetime_with_fractional_seconds() -> None:
    result = parse_exif_datetime("2024:07:15 12:30:45.123")

    assert result == datetime(2024, 7, 15, 12, 30, 45, 123000)


def test_parse_iso_like_datetime() -> None:
    result = parse_exif_datetime("2024-07-15T12:30:45")

    assert result == datetime(2024, 7, 15, 12, 30, 45)


def test_parse_invalid_datetime_returns_none() -> None:
    assert parse_exif_datetime(None) is None
    assert parse_exif_datetime("") is None
    assert parse_exif_datetime("not a date") is None
    assert parse_exif_datetime("2024:99:99 99:99:99") is None


def test_dimensions_are_unchanged_without_rotation() -> None:
    assert get_display_dimensions(4032, 3024, None) == (4032, 3024)
    assert get_display_dimensions(4032, 3024, 1) == (4032, 3024)
    assert get_display_dimensions(4032, 3024, 3) == (4032, 3024)


def test_dimensions_are_swapped_for_90_degree_orientations() -> None:
    assert get_display_dimensions(4032, 3024, 5) == (3024, 4032)
    assert get_display_dimensions(4032, 3024, 6) == (3024, 4032)
    assert get_display_dimensions(4032, 3024, 7) == (3024, 4032)
    assert get_display_dimensions(4032, 3024, 8) == (3024, 4032)


def test_invalid_orientation_does_not_change_dimensions() -> None:
    assert get_display_dimensions(4032, 3024, "invalid") == (4032, 3024)
