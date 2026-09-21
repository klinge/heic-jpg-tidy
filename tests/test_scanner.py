# tests/test_scanner.py
from pathlib import Path

import pytest

from heic_jpg_tidy.scanner import (
    find_file_groups,
    is_heic_file,
    is_jpg_file,
    is_supported_image,
)


def create_file(path: Path) -> Path:
    """Create an empty test file, including missing parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def test_supported_file_extensions_are_recognized() -> None:
    assert is_supported_image(Path("IMG_0001.HEIC"))
    assert is_supported_image(Path("IMG_0001.heif"))
    assert is_supported_image(Path("IMG_0001.JPG"))
    assert is_supported_image(Path("IMG_0001.jpeg"))

    assert not is_supported_image(Path("IMG_0001.png"))
    assert not is_supported_image(Path("IMG_0001.mov"))
    assert not is_supported_image(Path("IMG_0001.xmp"))
    assert not is_supported_image(Path("IMG_0001"))


def test_heic_and_jpg_extensions_are_classified() -> None:
    assert is_heic_file(Path("IMG_0001.HEIC"))
    assert is_heic_file(Path("IMG_0001.heif"))
    assert not is_heic_file(Path("IMG_0001.JPG"))

    assert is_jpg_file(Path("IMG_0001.JPG"))
    assert is_jpg_file(Path("IMG_0001.jpeg"))
    assert not is_jpg_file(Path("IMG_0001.HEIC"))


def test_finds_unambiguous_pair_in_same_directory(tmp_path: Path) -> None:
    create_file(tmp_path / "2024" / "IMG_1234.HEIC")
    create_file(tmp_path / "2024" / "IMG_1234.JPG")

    groups = find_file_groups(tmp_path)

    assert len(groups) == 1

    group = groups[0]
    assert group.directory == tmp_path / "2024"
    assert group.stem == "img_1234"
    assert group.heic_paths == (tmp_path / "2024" / "IMG_1234.HEIC",)
    assert group.jpg_paths == (tmp_path / "2024" / "IMG_1234.JPG",)
    assert group.is_unambiguous_pair is True


def test_filename_matching_is_case_insensitive(tmp_path: Path) -> None:
    create_file(tmp_path / "IMG_1234.HEIC")
    create_file(tmp_path / "img_1234.jpg")

    groups = find_file_groups(tmp_path)

    assert len(groups) == 1
    assert groups[0].stem == "img_1234"
    assert groups[0].is_unambiguous_pair is True


def test_same_stem_in_different_directories_creates_separate_groups(
    tmp_path: Path,
) -> None:
    create_file(tmp_path / "2023" / "IMG_1234.HEIC")
    create_file(tmp_path / "2023" / "IMG_1234.JPG")

    create_file(tmp_path / "2024" / "IMG_1234.HEIC")
    create_file(tmp_path / "2024" / "IMG_1234.JPG")

    groups = find_file_groups(tmp_path)

    assert len(groups) == 2
    assert {group.directory for group in groups} == {
        tmp_path / "2023",
        tmp_path / "2024",
    }


def test_ignores_groups_without_both_heic_and_jpg(tmp_path: Path) -> None:
    create_file(tmp_path / "HEIC_only.HEIC")
    create_file(tmp_path / "JPG_only.JPG")
    create_file(tmp_path / "document.pdf")
    create_file(tmp_path / "video.mov")

    groups = find_file_groups(tmp_path)

    assert groups == []


def test_ignores_symbolic_link_images(tmp_path: Path) -> None:
    target_file = create_file(tmp_path / "real.JPG")
    linked_file = tmp_path / "IMG_1234.JPG"
    linked_file.symlink_to(target_file)
    create_file(tmp_path / "IMG_1234.HEIC")

    groups = find_file_groups(tmp_path)

    assert groups == []
    assert linked_file.is_symlink()
    assert target_file.exists()


def test_multiple_jpg_files_create_ambiguous_group(tmp_path: Path) -> None:
    create_file(tmp_path / "IMG_1234.HEIC")
    create_file(tmp_path / "IMG_1234.JPG")
    create_file(tmp_path / "IMG_1234.JPEG")

    groups = find_file_groups(tmp_path)

    assert len(groups) == 1

    group = groups[0]
    assert group.heic_paths == (tmp_path / "IMG_1234.HEIC",)
    assert group.jpg_paths == (
        tmp_path / "IMG_1234.JPEG",
        tmp_path / "IMG_1234.JPG",
    )
    assert group.is_unambiguous_pair is False


def test_multiple_heic_files_create_ambiguous_group(tmp_path: Path) -> None:
    create_file(tmp_path / "IMG_1234.HEIC")
    create_file(tmp_path / "IMG_1234.HEIF")
    create_file(tmp_path / "IMG_1234.JPG")

    groups = find_file_groups(tmp_path)

    assert len(groups) == 1
    assert groups[0].is_unambiguous_pair is False


def test_raises_for_missing_source_directory(tmp_path: Path) -> None:
    missing_directory = tmp_path / "does_not_exist"

    with pytest.raises(NotADirectoryError):
        find_file_groups(missing_directory)
