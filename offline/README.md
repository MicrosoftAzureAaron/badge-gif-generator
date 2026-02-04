# Badge GIF Generator - Offline Mode

Create animated GIFs from your certification badges with a local web interface. This standalone version runs entirely on your machine without cloud dependencies.

## Features

- **Web Interface**: Modern, user-friendly interface with drag-and-drop reordering
- **Badge Library**: Organize badges by category in folders
- **Multiple Sources**: Use library badges, upload files, or paste image URLs
- **Customizable**: Adjust duration, canvas size, background color, and badges per frame
- **Transparent Backgrounds**: Optional transparent GIF output
- **Auto-Save**: Generated GIFs are automatically saved to the output folder

## Quick Start

### Windows (Double-click)

1. Double-click `run.bat` to start the server
2. Your browser will open automatically to http://localhost:5000

### PowerShell

```powershell
.\run.ps1
# First run will create virtual environment and install dependencies
```

### Manual Setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m src.server
```

## Folder Structure

```
Off Line/
├── input/
│   ├── badges/          # Put badge images here
│   │   ├── Azure/       # Organize by category (optional)
│   │   ├── AWS/
│   │   └── CompTIA/
│   └── Logos/           # Put company logos here
├── output/              # Generated GIFs saved here
├── frontend/            # Web interface files
└── src/                 # Python source code
```

## Adding Badges

1. Add badge images (PNG, JPG, GIF, BMP, WebP) to `input/badges/`
2. Organize into subfolders for category tabs (e.g., `badges/Azure/`, `badges/AWS/`)
3. Restart the server to load new badges

## Adding Logos

1. Add logo images to `input/Logos/`
2. Logos appear at the end of the animation with longer duration

## CLI Tool (Original)

The original command-line tool is still available:

```powershell
python src/badge_gif_cli.py input/badges --output output/cert_badges.gif --duration 1200 --loop 0
```

### CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `input_folder` | Directory containing badge images | Required |
| `--output` | Output GIF path | `badge_slideshow.gif` |
| `--duration` | Frame duration in ms | 1500 |
| `--logo-duration` | Logo frame duration in ms | 2500 |
| `--loop` | Loop count (0 = infinite) | 0 |
| `--size` | Canvas size (WIDTHxHEIGHT) | 320x180 |
| `--background` | Background color | #FFFFFF |
| `--group-size` | Badges per frame | 3 |
| `-y, --yes` | Skip confirmation prompts | False |

## Requirements

- Python 3.8 or later
- Pillow (image processing)
- Flask (web server)
- Flask-CORS (cross-origin support)

All dependencies are installed automatically via `requirements.txt`.

## Troubleshooting

**Server won't start**: Make sure port 5000 isn't in use. Check firewall settings.

**Badges not loading**: Add images to `input/badges/` and restart the server.

**GIF quality issues**: Use PNG badges for best results. JPG may have compression artifacts.

## See Also

- **Azure Function and Site**: Cloud-hosted version with Azure Blob Storage integration

