"""
Core GIF generation logic - adapted from the offline CLI script.
Provides reusable functions for creating animated GIFs from badge and logo images.

Version: 1.1.0
"""

from dataclasses import dataclass
from io import BytesIO
from typing import List, Sequence, Tuple

from PIL import Image, ImageColor, ImageOps


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
    """Parse a color string into RGBA tuple. Returns (0,0,0,0) for 'transparent'."""
    if color_text.lower() == 'transparent':
        return (0, 0, 0, 0)
    try:
        color = ImageColor.getrgb(color_text)
        if len(color) == 3:
            return (*color, 255)
        return color
    except Exception as exc:
        raise ValueError(f"Invalid color: {color_text}. Use hex (#FFFFFF), color name, or 'transparent'.") from exc


def parse_size(size_text: str) -> Tuple[int, int]:
    """Parse a size string (WIDTHxHEIGHT) into a tuple."""
    if not size_text:
        return DEFAULT_CONFIG.size
    try:
        width_text, height_text = size_text.lower().split("x", maxsplit=1)
        width = int(width_text)
        height = int(height_text)
        if width <= 0 or height <= 0:
            raise ValueError("Dimensions must be positive")
        if width > 2000 or height > 2000:
            raise ValueError("Maximum dimension is 2000px")
        return width, height
    except ValueError as exc:
        raise ValueError(
            f"Size must be WIDTHxHEIGHT (e.g., 320x180). Got: {size_text}"
        ) from exc


def compose_badge_frame(
    image: Image.Image,
    size: Tuple[int, int],
    background_color: Tuple[int, int, int, int],
    padding: int,
) -> Image.Image:
    """Create a single-badge frame centered on the canvas."""
    canvas = Image.new("RGBA", size, color=background_color)
    safe_width = max(1, size[0] - padding * 2)
    safe_height = max(1, size[1] - padding * 2)
    badge = ImageOps.contain(
        image,
        (safe_width, safe_height),
        Image.Resampling.LANCZOS,
    )
    offset = ((size[0] - badge.width) // 2, (size[1] - badge.height) // 2)
    canvas.paste(badge, offset, badge if badge.mode == "RGBA" else None)
    return canvas


def compose_multi_badge_frame(
    images: Sequence[Image.Image],
    size: Tuple[int, int],
    background_color: Tuple[int, int, int, int],
    padding: int,
) -> Image.Image:
    """Create a frame with multiple badges arranged horizontally."""
    if not images:
        raise ValueError("At least one image is required.")

    if len(images) == 1:
        return compose_badge_frame(images[0], size, background_color, padding)

    canvas = Image.new("RGBA", size, color=background_color)
    safe_width = max(1, size[0] - padding * 2)
    safe_height = max(1, size[1] - padding * 2)
    spacing = padding if len(images) > 1 else 0
    available_width = max(1, safe_width - spacing * (len(images) - 1))
    column_width = max(1, available_width // len(images))
    total_content_width = column_width * len(images) + spacing * (len(images) - 1)
    start_x = padding + (safe_width - total_content_width) // 2

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
    return canvas


def group_images(images: Sequence[Image.Image], group_size: int) -> List[List[Image.Image]]:
    """Group images into batches of specified size, padding the last group if needed."""
    if not images:
        return []

    groups: List[List[Image.Image]] = []
    index = 0
    total = len(images)
    
    while index + group_size <= total:
        groups.append(list(images[index:index + group_size]))
        index += group_size

    remainder = list(images[index:])
    if remainder:
        pad_index = 0
        while len(remainder) < group_size and images:
            remainder.append(images[pad_index % len(images)])
            pad_index += 1
        groups.append(remainder)
    elif not groups and images:
        groups.append([images[0]] * group_size)
    
    return groups


def has_transparency(image: Image.Image) -> bool:
    """
    Check if an image has meaningful transparency.
    
    Returns True if the image has an alpha channel with non-fully-opaque pixels.
    """
    if image.mode != "RGBA":
        return False
    
    # Get alpha channel
    alpha = image.split()[3]
    
    # Check if any pixel is not fully opaque (255)
    # We consider an image transparent if at least some pixels have alpha < 255
    extrema = alpha.getextrema()
    
    # If min alpha is less than 255, there's some transparency
    return extrema[0] < 255


def remove_white_background(image: Image.Image, threshold: int = 250) -> Image.Image:
    """
    Remove white/near-white background from an image.
    
    Pixels where R, G, and B are all >= threshold are made transparent.
    Uses edge detection to preserve anti-aliased edges.
    
    Args:
        image: Input image in RGBA mode
        threshold: Minimum value for R, G, B to consider a pixel as white (0-255)
        
    Returns:
        Image with white background removed
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    
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
    
    return result


def load_image_from_bytes(image_data: bytes, remove_white_bg: bool = False, white_threshold: int = 250) -> Image.Image:
    """
    Load an image from bytes and convert to RGBA.
    
    Args:
        image_data: Raw image bytes
        remove_white_bg: If True, remove white background from images without transparency
        white_threshold: Threshold for white detection (0-255)
        
    Returns:
        Image in RGBA mode, optionally with white background removed
    """
    image = Image.open(BytesIO(image_data))
    image = image.convert("RGBA")
    
    # If remove_white_bg is enabled and image doesn't already have transparency
    if remove_white_bg and not has_transparency(image):
        image = remove_white_background(image, white_threshold)
    
    return image


def generate_gif(
    badge_images: List[Image.Image],
    logo_images: List[Image.Image],
    config: GifConfig,
) -> bytes:
    """
    Generate an animated GIF from badge and logo images.
    
    Args:
        badge_images: List of badge images (grouped into frames)
        logo_images: List of logo images (each becomes a separate frame)
        config: GIF generation configuration
        
    Returns:
        The generated GIF as bytes
    """
    background_color = parse_color(config.background)
    frames: List[Image.Image] = []
    durations: List[int] = []

    # Process badges (grouped)
    if badge_images:
        grouped_badges = group_images(badge_images, config.group_size)
        for group in grouped_badges:
            frame = compose_multi_badge_frame(group, config.size, background_color, config.padding)
            frames.append(frame)
            durations.append(config.duration)

    # Process logos (one per frame)
    for logo in logo_images:
        frame = compose_badge_frame(logo, config.size, background_color, config.padding)
        frames.append(frame)
        durations.append(config.logo_duration)

    if not frames:
        raise ValueError("No images provided to generate GIF.")

    # Create the GIF
    output = BytesIO()
    first_frame = frames[0]
    additional_frames = frames[1:] if len(frames) > 1 else []
    
    # Check if transparent background
    is_transparent = config.background.lower() == 'transparent'
    
    # Convert frames for GIF (handle transparency)
    if is_transparent:
        # For transparent GIFs, convert to P mode with transparency
        def convert_frame(frame):
            # Use alpha channel as transparency mask
            alpha = frame.split()[3]
            p_frame = frame.convert('P', palette=Image.Palette.ADAPTIVE, colors=255)
            # Set transparency for pixels that were transparent
            mask = Image.eval(alpha, lambda a: 255 if a < 128 else 0)
            p_frame.paste(255, mask)  # 255 will be our transparent color
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
        # Convert RGBA to P mode for non-transparent GIFs
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


def generate_gif_from_bytes(
    badge_data: List[bytes],
    logo_data: List[bytes],
    config: GifConfig,
) -> bytes:
    """
    Generate a GIF from raw image bytes.
    
    Args:
        badge_data: List of badge images as bytes
        logo_data: List of logo images as bytes
        config: GIF generation configuration
        
    Returns:
        The generated GIF as bytes
    """
    badge_images = [
        load_image_from_bytes(data, config.remove_white_bg, config.white_threshold) 
        for data in badge_data
    ]
    logo_images = [
        load_image_from_bytes(data, config.remove_white_bg, config.white_threshold) 
        for data in logo_data
    ]
    return generate_gif(badge_images, logo_images, config)
