"""
Tests for the GIF Generator module.
"""

import pytest
from io import BytesIO
from PIL import Image

from gif_generator import (
    GifConfig,
    parse_color,
    parse_size,
    compose_badge_frame,
    compose_multi_badge_frame,
    group_images,
    load_image_from_bytes,
    generate_gif,
    generate_gif_from_bytes,
)


def create_test_image(width: int = 100, height: int = 100, color: str = "red") -> Image.Image:
    """Create a simple test image."""
    return Image.new("RGBA", (width, height), color)


def create_test_image_bytes(width: int = 100, height: int = 100, color: str = "red") -> bytes:
    """Create a test image as bytes."""
    img = create_test_image(width, height, color)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


class TestParseColor:
    """Tests for parse_color function."""

    def test_hex_color(self):
        result = parse_color("#FF0000")
        assert result == (255, 0, 0, 255)

    def test_hex_color_lowercase(self):
        result = parse_color("#00ff00")
        assert result == (0, 255, 0, 255)

    def test_color_name(self):
        result = parse_color("blue")
        assert result == (0, 0, 255, 255)

    def test_invalid_color(self):
        with pytest.raises(ValueError):
            parse_color("notacolor123")


class TestParseSize:
    """Tests for parse_size function."""

    def test_valid_size(self):
        result = parse_size("320x180")
        assert result == (320, 180)

    def test_valid_size_uppercase(self):
        result = parse_size("400X300")
        assert result == (400, 300)

    def test_default_size(self):
        result = parse_size("")
        assert result == (320, 180)

    def test_none_size(self):
        result = parse_size(None)
        assert result == (320, 180)

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_size("320-180")

    def test_negative_dimension(self):
        with pytest.raises(ValueError):
            parse_size("-320x180")

    def test_zero_dimension(self):
        with pytest.raises(ValueError):
            parse_size("0x180")

    def test_too_large_dimension(self):
        with pytest.raises(ValueError):
            parse_size("3000x180")


class TestComposeBadgeFrame:
    """Tests for compose_badge_frame function."""

    def test_creates_correct_size(self):
        image = create_test_image(100, 100)
        result = compose_badge_frame(image, (320, 180), (255, 255, 255, 255), 5)
        assert result.size == (320, 180)

    def test_rgba_output(self):
        image = create_test_image(100, 100)
        result = compose_badge_frame(image, (320, 180), (255, 255, 255, 255), 5)
        assert result.mode == "RGBA"


class TestComposeMultiBadgeFrame:
    """Tests for compose_multi_badge_frame function."""

    def test_single_image(self):
        images = [create_test_image(100, 100)]
        result = compose_multi_badge_frame(images, (320, 180), (255, 255, 255, 255), 5)
        assert result.size == (320, 180)

    def test_multiple_images(self):
        images = [create_test_image(100, 100, color) for color in ["red", "green", "blue"]]
        result = compose_multi_badge_frame(images, (320, 180), (255, 255, 255, 255), 5)
        assert result.size == (320, 180)

    def test_empty_list_raises(self):
        with pytest.raises(ValueError):
            compose_multi_badge_frame([], (320, 180), (255, 255, 255, 255), 5)


class TestGroupImages:
    """Tests for group_images function."""

    def test_exact_groups(self):
        images = [create_test_image() for _ in range(6)]
        groups = group_images(images, 3)
        assert len(groups) == 2
        assert all(len(g) == 3 for g in groups)

    def test_remainder_padded(self):
        images = [create_test_image() for _ in range(5)]
        groups = group_images(images, 3)
        assert len(groups) == 2
        assert len(groups[0]) == 3
        assert len(groups[1]) == 3  # Padded

    def test_empty_list(self):
        groups = group_images([], 3)
        assert groups == []

    def test_fewer_than_group_size(self):
        images = [create_test_image() for _ in range(2)]
        groups = group_images(images, 3)
        assert len(groups) == 1
        assert len(groups[0]) == 3  # Padded


class TestLoadImageFromBytes:
    """Tests for load_image_from_bytes function."""

    def test_loads_png(self):
        data = create_test_image_bytes()
        image = load_image_from_bytes(data)
        assert image.mode == "RGBA"

    def test_preserves_size(self):
        data = create_test_image_bytes(200, 150)
        image = load_image_from_bytes(data)
        assert image.size == (200, 150)


class TestGenerateGif:
    """Tests for generate_gif function."""

    def test_generates_gif_with_badges(self):
        badges = [create_test_image(100, 100, color) for color in ["red", "green", "blue"]]
        config = GifConfig()
        result = generate_gif(badges, [], config)
        
        assert isinstance(result, bytes)
        assert len(result) > 0
        
        # Verify it's a valid GIF
        gif = Image.open(BytesIO(result))
        assert gif.format == "GIF"

    def test_generates_gif_with_logos(self):
        logos = [create_test_image(100, 100, color) for color in ["yellow", "purple"]]
        config = GifConfig()
        result = generate_gif([], logos, config)
        
        gif = Image.open(BytesIO(result))
        assert gif.format == "GIF"

    def test_generates_gif_with_both(self):
        badges = [create_test_image(100, 100, "red")]
        logos = [create_test_image(100, 100, "blue")]
        config = GifConfig()
        result = generate_gif(badges, logos, config)
        
        gif = Image.open(BytesIO(result))
        assert gif.format == "GIF"

    def test_empty_inputs_raises(self):
        config = GifConfig()
        with pytest.raises(ValueError):
            generate_gif([], [], config)

    def test_custom_config(self):
        badges = [create_test_image(100, 100)]
        config = GifConfig(
            size=(400, 225),
            background="#000000",
            padding=10,
            group_size=2,
            duration=2000,
        )
        result = generate_gif(badges, [], config)
        
        gif = Image.open(BytesIO(result))
        assert gif.size == (400, 225)


class TestGenerateGifFromBytes:
    """Tests for generate_gif_from_bytes function."""

    def test_generates_from_bytes(self):
        badge_data = [create_test_image_bytes(100, 100, color) for color in ["red", "green"]]
        logo_data = [create_test_image_bytes(100, 100, "blue")]
        config = GifConfig()
        
        result = generate_gif_from_bytes(badge_data, logo_data, config)
        
        assert isinstance(result, bytes)
        gif = Image.open(BytesIO(result))
        assert gif.format == "GIF"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
