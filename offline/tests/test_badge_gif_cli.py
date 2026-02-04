"""Unit tests for badge_gif_cli module."""

import tempfile
from pathlib import Path

import pytest
from PIL import Image

from src.badge_gif_cli import (
    Config,
    DEFAULT_CONFIG,
    compose_badge_frame,
    compose_multi_badge_frame,
    find_image_files,
    group_badge_paths,
    parse_color,
    parse_size,
    resolve_unique_path,
)


class TestConfig:
    """Tests for the Config dataclass."""

    def test_default_config_values(self) -> None:
        assert DEFAULT_CONFIG.size == (320, 180)
        assert DEFAULT_CONFIG.background == "#FFFFFF"
        assert DEFAULT_CONFIG.padding == 5
        assert DEFAULT_CONFIG.group_size == 3
        assert DEFAULT_CONFIG.duration == 1500
        assert DEFAULT_CONFIG.logo_duration == 2500
        assert DEFAULT_CONFIG.loop == 0

    def test_config_is_frozen(self) -> None:
        with pytest.raises(AttributeError):
            DEFAULT_CONFIG.padding = 10  # type: ignore[misc]

    def test_custom_config(self) -> None:
        custom = Config(size=(640, 360), padding=10)
        assert custom.size == (640, 360)
        assert custom.padding == 10
        assert custom.background == "#FFFFFF"  # default preserved


class TestParseColor:
    """Tests for parse_color function."""

    def test_hex_color_rgb(self) -> None:
        assert parse_color("#FF0000") == (255, 0, 0, 255)

    def test_hex_color_short(self) -> None:
        assert parse_color("#F00") == (255, 0, 0, 255)

    def test_named_color(self) -> None:
        result = parse_color("red")
        assert result == (255, 0, 0, 255)

    def test_rgba_color(self) -> None:
        result = parse_color("rgba(128, 64, 32, 200)")
        assert result == (128, 64, 32, 200)

    def test_invalid_color_raises(self) -> None:
        with pytest.raises(ValueError, match="valid Pillow color"):
            parse_color("not-a-color")


class TestParseSize:
    """Tests for parse_size function."""

    def test_valid_size(self) -> None:
        assert parse_size("640x480") == (640, 480)

    def test_uppercase_x(self) -> None:
        assert parse_size("800X600") == (800, 600)

    def test_none_returns_default(self) -> None:
        assert parse_size(None) == DEFAULT_CONFIG.size

    def test_empty_string_returns_default(self) -> None:
        assert parse_size("") == DEFAULT_CONFIG.size

    def test_invalid_format_raises(self) -> None:
        with pytest.raises(ValueError, match="WIDTHxHEIGHT"):
            parse_size("invalid")

    def test_negative_dimension_raises(self) -> None:
        with pytest.raises(ValueError, match="positive integers"):
            parse_size("-100x200")

    def test_zero_dimension_raises(self) -> None:
        with pytest.raises(ValueError, match="positive integers"):
            parse_size("0x200")


class TestGroupBadgePaths:
    """Tests for group_badge_paths function."""

    def test_empty_list(self) -> None:
        assert group_badge_paths([], 3) == []

    def test_exact_multiple(self) -> None:
        paths = [Path(f"badge{i}.png") for i in range(6)]
        groups = group_badge_paths(paths, 3)
        assert len(groups) == 2
        assert all(len(g) == 3 for g in groups)

    def test_remainder_padded(self) -> None:
        paths = [Path(f"badge{i}.png") for i in range(5)]
        groups = group_badge_paths(paths, 3)
        assert len(groups) == 2
        assert len(groups[0]) == 3
        assert len(groups[1]) == 3  # padded
        assert groups[1][0] == paths[3]
        assert groups[1][1] == paths[4]
        assert groups[1][2] == paths[0]  # wraps to first

    def test_single_badge_padded(self) -> None:
        paths = [Path("badge.png")]
        groups = group_badge_paths(paths, 3)
        assert len(groups) == 1
        assert len(groups[0]) == 3
        assert all(p == paths[0] for p in groups[0])

    def test_two_badges_padded(self) -> None:
        paths = [Path("a.png"), Path("b.png")]
        groups = group_badge_paths(paths, 3)
        assert len(groups) == 1
        assert len(groups[0]) == 3
        assert groups[0] == [paths[0], paths[1], paths[0]]

    def test_custom_group_size(self) -> None:
        paths = [Path(f"badge{i}.png") for i in range(7)]
        groups = group_badge_paths(paths, 4)
        assert len(groups) == 2
        assert len(groups[0]) == 4
        assert len(groups[1]) == 4  # 3 originals + 1 padded


class TestResolveUniquePath:
    """Tests for resolve_unique_path function."""

    def test_non_existing_path_unchanged(self, tmp_path: Path) -> None:
        target = tmp_path / "output.gif"
        assert resolve_unique_path(target) == target

    def test_existing_path_incremented(self, tmp_path: Path) -> None:
        target = tmp_path / "output.gif"
        target.touch()
        result = resolve_unique_path(target)
        assert result == tmp_path / "output-1.gif"

    def test_multiple_existing_paths(self, tmp_path: Path) -> None:
        (tmp_path / "output.gif").touch()
        (tmp_path / "output-1.gif").touch()
        (tmp_path / "output-2.gif").touch()
        result = resolve_unique_path(tmp_path / "output.gif")
        assert result == tmp_path / "output-3.gif"


class TestFindImageFiles:
    """Tests for find_image_files function."""

    def test_finds_badges_and_logos(self, tmp_path: Path) -> None:
        badges_dir = tmp_path / "badges"
        badges_dir.mkdir()
        logo_dir = tmp_path / "logo"
        logo_dir.mkdir()

        (badges_dir / "badge1.png").touch()
        (badges_dir / "badge2.jpg").touch()
        (logo_dir / "company.png").touch()

        badges, logos = find_image_files(tmp_path)
        assert len(badges) == 2
        assert len(logos) == 1

    def test_empty_folder_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="No supported image files"):
            find_image_files(tmp_path)

    def test_nonexistent_folder_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="Input folder not found"):
            find_image_files(tmp_path / "nonexistent")

    def test_ignores_non_image_files(self, tmp_path: Path) -> None:
        (tmp_path / "readme.txt").touch()
        (tmp_path / "data.json").touch()
        (tmp_path / "valid.png").touch()

        badges, logos = find_image_files(tmp_path)
        assert len(badges) == 1
        assert badges[0].name == "valid.png"


class TestComposeBadgeFrame:
    """Tests for compose_badge_frame function."""

    def test_creates_correct_size(self) -> None:
        image = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
        frame = compose_badge_frame(image, (320, 180), (255, 255, 255, 255), 5)
        assert frame.size == (320, 180)

    def test_background_color_applied(self) -> None:
        image = Image.new("RGBA", (10, 10), color=(255, 0, 0, 255))
        frame = compose_badge_frame(image, (100, 100), (0, 255, 0, 255), 5)
        # Check corner pixel is background color
        assert frame.getpixel((0, 0)) == (0, 255, 0, 255)


class TestComposeMultiBadgeFrame:
    """Tests for compose_multi_badge_frame function."""

    def test_single_image_delegates(self) -> None:
        image = Image.new("RGBA", (100, 100), color=(255, 0, 0, 255))
        frame = compose_multi_badge_frame([image], (320, 180), (255, 255, 255, 255), 5)
        assert frame.size == (320, 180)

    def test_multiple_images(self) -> None:
        images = [
            Image.new("RGBA", (100, 100), color=(255, 0, 0, 255)),
            Image.new("RGBA", (100, 100), color=(0, 255, 0, 255)),
            Image.new("RGBA", (100, 100), color=(0, 0, 255, 255)),
        ]
        frame = compose_multi_badge_frame(images, (320, 180), (255, 255, 255, 255), 5)
        assert frame.size == (320, 180)

    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValueError, match="requires at least one image"):
            compose_multi_badge_frame([], (320, 180), (255, 255, 255, 255), 5)
