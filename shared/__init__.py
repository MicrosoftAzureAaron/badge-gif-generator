"""
Shared code for Badge GIF Generator.
Contains core GIF generation logic used by both Azure VM and Offline deployments.
"""

from .gif_generator import (
    GifConfig,
    DEFAULT_CONFIG,
    parse_color,
    parse_size,
    compose_badge_frame,
    compose_multi_badge_frame,
    group_images,
    load_image_from_bytes,
    generate_gif,
    generate_gif_from_bytes,
)

__all__ = [
    "GifConfig",
    "DEFAULT_CONFIG", 
    "parse_color",
    "parse_size",
    "compose_badge_frame",
    "compose_multi_badge_frame",
    "group_images",
    "load_image_from_bytes",
    "generate_gif",
    "generate_gif_from_bytes",
]
