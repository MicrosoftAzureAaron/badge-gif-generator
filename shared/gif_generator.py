"""
Core GIF generation logic - adapted from the offline CLI script.
Provides reusable functions for creating animated GIFs from badge and logo images.

This module handles:
- Image composition and layout
- Color parsing and validation
- GIF encoding with frame management
- Transparency and background removal

Version: 1.1.1
"""

import logging
from dataclasses import dataclass
from io import BytesIO
from typing import List, Sequence, Tuple

from PIL import Image, ImageColor, ImageOps

# Configure module logger
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())


@dataclass(frozen=True)
class GifConfig:
    """Configuration for GIF generation."""
    
    size: Tuple[int, int] = (320, 180)
    background: str = "#FFFFFF"
    padding: int = 5
    group_size: int = 3
    duration: int = 1500
    logo_duration: int = 2500
    loop: int = 0
    remove_white_bg: bool = False
    white_threshold: int = 250  # Pixels with R,G,B all >= this are considered white


DEFAULT_CONFIG = GifConfig()


def parse_color(color_text: str) -> Tuple[int, int, int, int]:
    """
    Parse a color string into RGBA tuple.
    
    Supports:
    - Hex colors: #FFFFFF, #FFF (with alpha: #FFFFFF80)
    - CSS color names: red, blue, transparent
    - Named transparency: 'transparent' returns (0, 0, 0, 0)
    
    Args:
        color_text: Color specification string
        
    Returns:
        RGBA tuple (0-255 for each channel)
        
    Raises:
        ValueError: If color_text is not a valid color format
    """
    if not color_text or not isinstance(color_text, str):
        logger.warning(f"Invalid color_text type or empty: {color_text!r}, using white")
        return (255, 255, 255, 255)
    
    if color_text.lower() == 'transparent':
        logger.debug("Color parsed as transparent")
        return (0, 0, 0, 0)
    
    try:
        # Try parsing with ImageColor
        color = ImageColor.getrgb(color_text)
        
        # Handle 3-tuple (RGB) by adding full alpha
        if len(color) == 3:
            result = (*color, 255)
        elif len(color) == 4:
            result = color
        else:
            raise ValueError(f"Unexpected color tuple length: {len(color)}")
        
        logger.debug(f"Color '{color_text}' parsed to RGBA: {result}")
        return result
    except ValueError as exc:
        logger.error(f"Failed to parse color '{color_text}': {exc}")
        raise ValueError(
            f"Invalid color: {color_text}. Use hex (#FFFFFF), CSS color name (red, blue), "
            f"or 'transparent'."
        ) from exc


def parse_size(size_text: str) -> Tuple[int, int]:
    """
    Parse a size string (WIDTHxHEIGHT) into a tuple.
    
    Args:
        size_text: Size specification in 'WIDTHxHEIGHT' format (e.g., '320x180')
                   If empty, returns default size
        
    Returns:
        Tuple of (width, height) in pixels
        
    Raises:
        ValueError: If size_text is invalid format or dimensions exceed limits
    """
    if not size_text:
        logger.debug(f"Empty size_text provided, using default: {DEFAULT_CONFIG.size}")
        return DEFAULT_CONFIG.size
    
    try:
        # Case-insensitive splitting
        parts = size_text.lower().split("x", maxsplit=1)
        if len(parts) != 2:
            raise ValueError(f"Expected format 'WIDTHxHEIGHT', got: {size_text}")
        
        width_text, height_text = parts
        width = int(width_text)
        height = int(height_text)
        
        # Validate dimensions
        if width <= 0 or height <= 0:
            raise ValueError(f"Dimensions must be positive (got {width}x{height})")
        if width > 2000 or height > 2000:
            raise ValueError(f"Maximum dimension is 2000px (got {width}x{height})")
        
        logger.debug(f"Size parsed: {width}x{height}")
        return width, height
    except (ValueError, AttributeError) as exc:
        logger.error(f"Failed to parse size '{size_text}': {exc}")
        raise ValueError(
            f"Size must be WIDTHxHEIGHT format (e.g., 320x180). Got: {size_text}"
        ) from exc


def compose_badge_frame(
    image: Image.Image,
    size: Tuple[int, int],
    background_color: Tuple[int, int, int, int],
    padding: int,
) -> Image.Image:
    """
    Create a single-badge frame centered on the canvas.
    
    Args:
        image: Badge image in RGBA mode
        size: Canvas size as (width, height)
        background_color: Canvas background as RGBA tuple
        padding: Padding around the badge in pixels
        
    Returns:
        Composed frame as Image.Image in RGBA mode
        
    Raises:
        ValueError: If image or size is invalid
    """
    if not isinstance(image, Image.Image):
        raise ValueError(f"Expected PIL Image, got {type(image)}")
    if size[0] <= 0 or size[1] <= 0:
        raise ValueError(f"Size must be positive: {size}")
    
    try:
        canvas = Image.new("RGBA", size, color=background_color)
        safe_width = max(1, size[0] - padding * 2)
        safe_height = max(1, size[1] - padding * 2)
        
        # Resize image to fit within safe area
        badge = ImageOps.contain(
            image,
            (safe_width, safe_height),
            Image.Resampling.LANCZOS,
        )
        
        # Center badge on canvas
        offset = ((size[0] - badge.width) // 2, (size[1] - badge.height) // 2)
        canvas.paste(badge, offset, badge if badge.mode == "RGBA" else None)
        
        logger.debug(f"Composed single badge frame: {size}, offset: {offset}")
        return canvas
    except Exception as exc:
        logger.error(f"Failed to compose badge frame: {exc}")
        raise


def compose_multi_badge_frame(
    images: Sequence[Image.Image],
    size: Tuple[int, int],
    background_color: Tuple[int, int, int, int],
    padding: int,
) -> Image.Image:
    """
    Create a frame with multiple badges arranged horizontally.
    
    If only one image is provided, it's centered (same as compose_badge_frame).
    Multiple images are arranged in a row with equal spacing.
    
    Args:
        images: Sequence of badge images in RGBA mode
        size: Canvas size as (width, height)
        background_color: Canvas background as RGBA tuple
        padding: Padding/spacing around and between badges
        
    Returns:
        Composed frame with multiple badges as Image.Image
        
    Raises:
        ValueError: If images list is empty or invalid
    """
    if not images:
        raise ValueError("At least one image is required for multi-badge frame.")
    
    if len(images) == 1:
        logger.debug("Only one image provided to multi-badge compose, using single-badge layout")
        return compose_badge_frame(images[0], size, background_color, padding)

    try:
        canvas = Image.new("RGBA", size, color=background_color)
        safe_width = max(1, size[0] - padding * 2)
        safe_height = max(1, size[1] - padding * 2)
        
        # Calculate spacing and dimensions for horizontal layout
        spacing = padding if len(images) > 1 else 0
        available_width = max(1, safe_width - spacing * (len(images) - 1))
        column_width = max(1, available_width // len(images))
        total_content_width = column_width * len(images) + spacing * (len(images) - 1)
        start_x = padding + (safe_width - total_content_width) // 2

        # Place each badge
        for index, image in enumerate(images):
            badge = ImageOps.contain(
                image,
                (column_width, safe_height),
                Image.Resampling.LANCZOS,
            )
            column_x = start_x + index * (column_width + spacing)
            x = column_x + (column_width - badge.width) // 2
            y = padding + (safe_height - badge.height) // 2
            canvas.paste(badge, (x, y), badge if badge.mode == "RGBA" else None)
        
        logger.debug(f"Composed multi-badge frame with {len(images)} badges")
        return canvas
    except Exception as exc:
        logger.error(f"Failed to compose multi-badge frame: {exc}")
        raise


def group_images(images: Sequence[Image.Image], group_size: int) -> List[List[Image.Image]]:
    """
    Group images into batches of specified size.
    
    Creates groups of group_size items. The final group may contain fewer items
    if the total number of images is not a multiple of group_size.
    
    Args:
        images: Sequence of images to group
        group_size: Number of images per group
        
    Returns:
        List of groups, each containing up to group_size images.
        The final group may have fewer items.
        
    Raises:
        ValueError: If images is empty or group_size <= 0
    """
    if not images:
        logger.warning("Empty images sequence provided to group_images")
        return []
    
    if group_size <= 0:
        raise ValueError(f"group_size must be positive, got {group_size}")

    try:
        groups: List[List[Image.Image]] = []
        index = 0
        total = len(images)
        
        # Create groups, allowing the last group to be incomplete
        while index < total:
            groups.append(list(images[index:index + group_size]))
            index += group_size
        
        logger.debug(f"Grouped {total} images into {len(groups)} groups (group_size={group_size})")
        return groups
    except Exception as exc:
        logger.error(f"Failed to group images: {exc}")
        raise


def has_transparency(image: Image.Image) -> bool:
    """
    Check if an image has meaningful transparency.
    
    Returns True if the image has an alpha channel with non-fully-opaque pixels.
    This is useful for determining whether to apply white background removal.
    
    Args:
        image: PIL Image to check
        
    Returns:
        True if image has partial or full transparency, False otherwise
        
    Raises:
        ValueError: If image is not a valid PIL Image
    """
    if not isinstance(image, Image.Image):
        raise ValueError(f"Expected PIL Image, got {type(image)}")
    
    if image.mode != "RGBA":
        logger.debug(f"Image mode is {image.mode}, not RGBA, assuming no transparency")
        return False
    
    try:
        # Get alpha channel
        alpha = image.split()[3]
        
        # Check if any pixel is not fully opaque (255)
        extrema = alpha.getextrema()
        
        # If min alpha is less than 255, there's some transparency
        has_trans = extrema[0] < 255
        logger.debug(f"Image has transparency: {has_trans} (alpha range: {extrema[0]}-{extrema[1]})")
        return has_trans
    except Exception as exc:
        logger.error(f"Error checking transparency: {exc}")
        return False


def remove_white_background(image: Image.Image, threshold: int = 250) -> Image.Image:
    """
    Remove white/near-white background from an image.
    
    Pixels where R, G, and B are all >= threshold are made transparent.
    Uses edge detection principles to preserve anti-aliased edges.
    
    Args:
        image: Input image in RGBA mode
        threshold: Minimum value for R, G, B to consider a pixel as white (0-255)
        
    Returns:
        New image with white background removed (RGBA mode)
        
    Raises:
        ValueError: If threshold is out of valid range
    """
    if not (0 <= threshold <= 255):
        raise ValueError(f"Threshold must be 0-255, got {threshold}")
    
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    
    try:
        # Get pixel data
        data = image.getdata()
        new_data = []
        
        for pixel in data:
            r, g, b, a = pixel
            
            # Check if pixel is white/near-white
            if r >= threshold and g >= threshold and b >= threshold:
                # Make it fully transparent
                new_data.append((r, g, b, 0))
            else:
                # Keep original pixel
                new_data.append(pixel)
        
        # Create new image with modified data
        result = Image.new("RGBA", image.size)
        result.putdata(new_data)
        
        logger.debug(f"Removed white background with threshold {threshold}")
        return result
    except Exception as exc:
        logger.error(f"Failed to remove white background: {exc}")
        raise


def load_image_from_bytes(image_data: bytes, remove_white_bg: bool = False, white_threshold: int = 250) -> Image.Image:
    """
    Load an image from bytes and convert to RGBA.
    
    Handles various image formats and optionally removes white background.
    
    Args:
        image_data: Raw image bytes (PNG, JPG, GIF, etc.)
        remove_white_bg: If True, remove white background from images without transparency
        white_threshold: Threshold for white detection (0-255)
        
    Returns:
        Image in RGBA mode, optionally with white background removed
        
    Raises:
        ValueError: If image_data is invalid or empty
        PIL.UnidentifiedImageError: If image format is not recognized
    """
    if not image_data:
        raise ValueError("image_data cannot be empty")
    
    try:
        # Load and convert to RGBA
        image = Image.open(BytesIO(image_data))
        image = image.convert("RGBA")
        
        logger.debug(f"Loaded image: {image.size}, mode: {image.mode}")
        
        # If remove_white_bg is enabled and image doesn't already have transparency
        if remove_white_bg and not has_transparency(image):
            logger.debug("Removing white background from image")
            image = remove_white_background(image, white_threshold)
        
        return image
    except Exception as exc:
        logger.error(f"Failed to load image from bytes: {exc}")
        raise ValueError(f"Invalid image data: {exc}") from exc


def generate_gif(
    badge_images: List[Image.Image],
    logo_images: List[Image.Image],
    config: GifConfig,
) -> bytes:
    """
    Generate an animated GIF from badge and logo images.
    
    Creates an animated GIF with:
    - Badges grouped into frames
    - Logos displayed individually (one per frame)
    - Custom duration, timing, and background settings
    
    Args:
        badge_images: List of badge images to display in groups
        logo_images: List of logo images to display individually
        config: GIF generation configuration (size, colors, timing, etc.)
        
    Returns:
        Generated GIF as bytes ready for download/storage
        
    Raises:
        ValueError: If no images provided or invalid configuration
    """
    try:
        background_color = parse_color(config.background)
        frames: List[Image.Image] = []
        durations: List[int] = []

        # Process badges (grouped)
        if badge_images:
            logger.info(f"Processing {len(badge_images)} badges into groups of {config.group_size}")
            grouped_badges = group_images(badge_images, config.group_size)
            for idx, group in enumerate(grouped_badges):
                frame = compose_multi_badge_frame(group, config.size, background_color, config.padding)
                frames.append(frame)
                durations.append(config.duration)
            logger.debug(f"Created {len(grouped_badges)} badge frames")

        # Process logos (one per frame)
        if logo_images:
            logger.info(f"Processing {len(logo_images)} logos")
            for logo in logo_images:
                frame = compose_badge_frame(logo, config.size, background_color, config.padding)
                frames.append(frame)
                durations.append(config.logo_duration)
            logger.debug(f"Created {len(logo_images)} logo frames")

        if not frames:
            raise ValueError("No images provided to generate GIF (need badges or logos)")

        logger.info(f"Generating GIF with {len(frames)} total frames")
        gif_bytes = _encode_gif_frames(frames, durations, config)
        logger.info(f"GIF generated successfully: {len(gif_bytes)} bytes")
        return gif_bytes
    except ValueError:
        # Re-raise ValueError as-is
        raise
    except Exception as exc:
        logger.error(f"Failed to generate GIF: {exc}")
        raise ValueError(f"GIF generation failed: {exc}") from exc


def generate_gif_from_bytes(
    badge_data: List[bytes],
    logo_data: List[bytes],
    config: GifConfig,
) -> bytes:
    """
    Generate a GIF from raw image bytes.
    
    Loads images from bytes, applies configurations, and generates GIF.
    This is the main entry point for API usage.
    
    Args:
        badge_data: List of badge image bytes
        logo_data: List of logo image bytes
        config: GIF generation configuration
        
    Returns:
        Generated GIF as bytes
        
    Raises:
        ValueError: If image data is invalid or configuration is incorrect
    """
    try:
        logger.info(f"Loading {len(badge_data)} badges and {len(logo_data)} logos from bytes")
        
        badge_images = [
            load_image_from_bytes(data, config.remove_white_bg, config.white_threshold) 
            for data in badge_data
        ]
        logo_images = [
            load_image_from_bytes(data, config.remove_white_bg, config.white_threshold) 
            for data in logo_data
        ]
        
        logger.info(f"Successfully loaded {len(badge_images)} badges and {len(logo_images)} logos")
        return generate_gif(badge_images, logo_images, config)
    except Exception as exc:
        logger.error(f"Failed to generate GIF from bytes: {exc}")
        raise


def generate_gif_from_ordered_bytes(
    ordered_items: List[Tuple[str, bytes]],
    config: GifConfig,
) -> bytes:
    """
    Generate a GIF while preserving an explicit ordered sequence of items.

    Badge items are grouped according to config.group_size and logo items are
    emitted as single frames. If logos appear between badges, pending badge
    groups are flushed before the logo frame so drag/drop order is respected.
    """
    try:
        ordered_images: List[Tuple[str, Image.Image]] = []
        for kind, data in ordered_items:
            if kind not in ("badge", "logo"):
                logger.warning(f"Skipping unknown ordered item kind: {kind}")
                continue
            image = load_image_from_bytes(data, config.remove_white_bg, config.white_threshold)
            ordered_images.append((kind, image))

        if not ordered_images:
            raise ValueError("No ordered images provided")

        background_color = parse_color(config.background)
        frames: List[Image.Image] = []
        durations: List[int] = []
        pending_badges: List[Image.Image] = []

        def flush_badges() -> None:
            if not pending_badges:
                return
            grouped = group_images(pending_badges, config.group_size)
            for group in grouped:
                frame = compose_multi_badge_frame(group, config.size, background_color, config.padding)
                frames.append(frame)
                durations.append(config.duration)
            pending_badges.clear()

        for kind, image in ordered_images:
            if kind == "badge":
                pending_badges.append(image)
            else:
                flush_badges()
                frame = compose_badge_frame(image, config.size, background_color, config.padding)
                frames.append(frame)
                durations.append(config.logo_duration)

        flush_badges()

        if not frames:
            raise ValueError("No frames generated from ordered images")

        return _encode_gif_frames(frames, durations, config)
    except Exception as exc:
        logger.error(f"Failed to generate ordered GIF: {exc}")
        raise


def _encode_gif_frames(
    frames: List[Image.Image],
    durations: List[int],
    config: GifConfig,
) -> bytes:
    """Encode prepared frames and durations into GIF bytes."""
    output = BytesIO()
    first_frame = frames[0]
    additional_frames = frames[1:] if len(frames) > 1 else []

    is_transparent = config.background.lower() == 'transparent'

    if is_transparent:
        logger.debug("Creating transparent GIF")

        def convert_frame(frame: Image.Image) -> Image.Image:
            alpha = frame.split()[3]
            p_frame = frame.convert('P', palette=Image.Palette.ADAPTIVE, colors=255)
            mask = Image.eval(alpha, lambda a: 255 if a < 128 else 0)
            p_frame.paste(255, mask)
            return p_frame

        first_frame_p = convert_frame(first_frame)
        additional_frames_p = [convert_frame(f) for f in additional_frames]

        first_frame_p.save(
            output,
            format="GIF",
            save_all=True,
            append_images=additional_frames_p,
            duration=durations,
            loop=config.loop,
            disposal=2,
            transparency=255,
        )
    else:
        logger.debug(f"Creating GIF with background color {config.background}")
        first_frame_p = first_frame.convert('P', palette=Image.Palette.ADAPTIVE)
        additional_frames_p = [f.convert('P', palette=Image.Palette.ADAPTIVE) for f in additional_frames]

        first_frame_p.save(
            output,
            format="GIF",
            save_all=True,
            append_images=additional_frames_p,
            duration=durations,
            loop=config.loop,
            disposal=2,
        )

    output.seek(0)
    return output.read()
