import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from PIL import Image, ImageColor, ImageOps

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"})
LOGO_FOLDER_NAMES = frozenset({"logo", "logos"})
MAX_FRAMES_WITHOUT_CONFIRM = 20


@dataclass(frozen=True)
class Config:
    """Default configuration values for the CLI."""

    size: tuple[int, int] = (320, 180)
    background: str = "#FFFFFF"
    padding: int = 5
    group_size: int = 3
    duration: int = 1500
    logo_duration: int = 2500
    loop: int = 0


DEFAULT_CONFIG = Config()


def parse_arguments(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Combine static badge images into an animated GIF for signatures or "
            "presentations."
        )
    )
    parser.add_argument(
        "input_folder",
        type=Path,
        help="Path to a folder containing badge images.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("badge_slideshow.gif"),
        help="Output GIF path (defaults to badge_slideshow.gif in the current directory).",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_CONFIG.duration,
        help=f"Frame duration in milliseconds (default: {DEFAULT_CONFIG.duration}).",
    )
    parser.add_argument(
        "--logo-duration",
        type=int,
        default=DEFAULT_CONFIG.logo_duration,
        help=f"Duration for logo slides in milliseconds (default: {DEFAULT_CONFIG.logo_duration}).",
    )
    parser.add_argument(
        "--loop",
        type=int,
        default=DEFAULT_CONFIG.loop,
        help=(
            "How many times to loop the animation (0 = infinite). GIF viewers should "
            "respect this flag."
        ),
    )
    parser.add_argument(
        "--size",
        type=str,
        default=f"{DEFAULT_CONFIG.size[0]}x{DEFAULT_CONFIG.size[1]}",
        help=(
            f"Target canvas size formatted as WIDTHxHEIGHT (default: {DEFAULT_CONFIG.size[0]}x{DEFAULT_CONFIG.size[1]}). "
            "Frames maintain aspect ratio within the canvas."
        ),
    )
    parser.add_argument(
        "--background",
        type=str,
        default=DEFAULT_CONFIG.background,
        help=f"Canvas background color (Pillow-compatible, default: {DEFAULT_CONFIG.background}).",
    )
    parser.add_argument(
        "--padding",
        type=int,
        default=DEFAULT_CONFIG.padding,
        help=f"Padding in pixels around badges (default: {DEFAULT_CONFIG.padding}).",
    )
    parser.add_argument(
        "--group-size",
        type=int,
        default=DEFAULT_CONFIG.group_size,
        help=f"Number of badges per slide (default: {DEFAULT_CONFIG.group_size}).",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation prompt for large frame counts.",
    )
    return parser.parse_args(argv)


def parse_color(color_text: str) -> tuple[int, int, int, int]:
    try:
        color = ImageColor.getrgb(color_text)
        if len(color) == 3:
            return (*color, 255)
        return color  # type: ignore[return-value]
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Background color must be a valid Pillow color string.") from exc


def resolve_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    index = 1
    while True:
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def parse_size(size_text: str | None) -> tuple[int, int]:
    if not size_text:
        return DEFAULT_CONFIG.size
    try:
        width_text, height_text = size_text.lower().split("x", maxsplit=1)
        width = int(width_text)
        height = int(height_text)
        if width <= 0 or height <= 0:
            raise ValueError
        return width, height
    except ValueError as exc:
        raise ValueError(
            "Size must be provided as WIDTHxHEIGHT with positive integers."
        ) from exc


def find_image_files(folder: Path) -> tuple[List[Path], List[Path]]:
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Input folder not found: {folder}")

    badges: List[Path] = []
    logos: List[Path] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        relative_parts = path.relative_to(folder).parts[:-1]
        if any(part.lower() in LOGO_FOLDER_NAMES for part in relative_parts):
            logos.append(path)
        else:
            badges.append(path)

    if not badges and not logos:
        raise FileNotFoundError(
            f"No supported image files found in {folder}. Supported extensions: "
            f"{', '.join(sorted(IMAGE_EXTENSIONS))}"
        )
    return badges, logos


def group_badge_paths(badges: Sequence[Path], group_size: int) -> List[List[Path]]:
    if not badges:
        return []

    groups: List[List[Path]] = []
    index = 0
    total = len(badges)
    while index + group_size <= total:
        groups.append(list(badges[index : index + group_size]))
        index += group_size

    remainder = list(badges[index:])
    if remainder:
        pad_index = 0
        while len(remainder) < group_size and badges:
            remainder.append(badges[pad_index % len(badges)])
            pad_index += 1
        groups.append(remainder)
    elif not groups and badges:
        groups.append([badges[0]] * group_size)
    return groups


def compose_badge_frame(
    image: Image.Image,
    size: tuple[int, int],
    background_color: tuple[int, int, int, int],
    padding: int,
) -> Image.Image:
    canvas = Image.new("RGBA", size, color=background_color)
    safe_width = max(1, size[0] - padding * 2)
    safe_height = max(1, size[1] - padding * 2)
    badge = ImageOps.contain(
        image,
        (safe_width, safe_height),
        Image.Resampling.LANCZOS,
    )
    offset = ((size[0] - badge.width) // 2, (size[1] - badge.height) // 2)
    canvas.paste(badge, offset, badge)
    return canvas


def compose_multi_badge_frame(
    images: Sequence[Image.Image],
    size: tuple[int, int],
    background_color: tuple[int, int, int, int],
    padding: int,
) -> Image.Image:
    if not images:
        raise ValueError("compose_multi_badge_frame requires at least one image.")

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
        canvas.paste(badge, (x, y), badge)
    return canvas


def create_frame_from_paths(
    group: Sequence[Path],
    size: tuple[int, int],
    background_color: tuple[int, int, int, int],
    padding: int,
) -> Image.Image:
    images: List[Image.Image] = []
    for image_path in group:
        with Image.open(image_path) as raw_image:
            images.append(raw_image.convert("RGBA").copy())
    return compose_multi_badge_frame(images, size, background_color, padding)


def load_frames(
    grouped_paths: Sequence[Sequence[Path]],
    size: tuple[int, int],
    background_color: tuple[int, int, int, int],
    padding: int,
) -> List[Image.Image]:
    frames: List[Image.Image] = []
    for group in grouped_paths:
        frame = create_frame_from_paths(group, size, background_color, padding)
        frames.append(frame)
    return frames


def save_gif(
    frames: Sequence[Image.Image],
    output_path: Path,
    durations: Sequence[int],
    loop: int,
) -> Path:
    target_path = resolve_unique_path(output_path)
    first_frame, *additional_frames = frames
    target_path.parent.mkdir(parents=True, exist_ok=True)
    first_frame.save(
        target_path,
        format="GIF",
        save_all=True,
        append_images=additional_frames,
        duration=list(durations),
        loop=loop,
        disposal=2,
    )
    return target_path


def main(argv: Iterable[str]) -> int:
    try:
        args = parse_arguments(argv)
        badge_paths, logo_paths = find_image_files(args.input_folder)
        grouped_badges = group_badge_paths(badge_paths, args.group_size)
        target_size = parse_size(args.size)
        background_color = parse_color(args.background)
        padding = args.padding
        frames: List[Image.Image] = []
        durations: List[int] = []

        if grouped_badges:
            badge_frames = load_frames(grouped_badges, target_size, background_color, padding)
            frames.extend(badge_frames)
            durations.extend([args.duration] * len(badge_frames))

        if logo_paths:
            logo_groups = [[path] for path in logo_paths]
            logo_frames = load_frames(logo_groups, target_size, background_color, padding)
            frames.extend(logo_frames)
            durations.extend([args.logo_duration] * len(logo_frames))

        if not frames:
            raise ValueError("No frames were generated. Check your inputs.")

        if len(frames) > MAX_FRAMES_WITHOUT_CONFIRM and not args.yes:
            print(f"This will generate {len(frames)} frames.")
            response = input("Continue? [y/N] ").strip().lower()
            if response not in ("y", "yes"):
                print("Aborted.")
                return 0

        final_output = save_gif(frames, args.output, durations, loop=args.loop)
        if final_output != args.output:
            print(
                "Existing file detected. Saved new animation as"
                f" {final_output} instead."
            )
        print(f"Created GIF with {len(frames)} frames at {final_output}")
        return 0
    except FileNotFoundError as not_found_err:
        print(f"Error: {not_found_err}", file=sys.stderr)
    except ValueError as value_err:
        print(f"Error: {value_err}", file=sys.stderr)
    except Exception as unexpected_err:  # noqa: BLE001
        print(f"Unexpected error: {unexpected_err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
