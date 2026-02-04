"""
Badge GIF Generator - Offline Local Server
Flask-based server that serves the web interface and generates GIFs locally.
Uses local folders for badge and logo libraries instead of Azure storage.
"""

import os
import sys
import json
import webbrowser
import threading
from io import BytesIO
from pathlib import Path
from typing import List

from flask import Flask, request, send_file, send_from_directory, jsonify, abort
from flask_cors import CORS
from PIL import Image

# Add shared module to path
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from shared.gif_generator import GifConfig, generate_gif_from_bytes

# Configuration
BASE_DIR = Path(__file__).parent.parent
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
FRONTEND_DIR = REPO_ROOT / "shared" / "frontend"  # Use shared frontend

BADGES_FOLDER = INPUT_DIR / "badges"
LOGOS_FOLDER = INPUT_DIR / "Logos"

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"})

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app)


def list_local_assets(folder: Path, asset_type: str) -> List[dict]:
    """List all image assets from a local folder."""
    assets = []
    
    if not folder.exists():
        return assets
    
    for item in folder.rglob("*"):
        if not item.is_file():
            continue
        
        ext = item.suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            continue
        
        # Get relative path from the folder
        rel_path = item.relative_to(folder)
        parts = rel_path.parts
        
        # Check if in a subfolder (category)
        if len(parts) > 1:
            category = parts[0].lower()
            filename_only = parts[-1]
        else:
            category = None
            filename_only = item.name
        
        base_name = item.stem
        display_name = base_name.replace("-", " ").replace("_", " ").title()
        tags = [t.lower() for t in base_name.replace("-", " ").replace("_", " ").split()]
        
        if asset_type == "logo":
            tags.append("logo")
        elif asset_type == "badge":
            tags.extend(["badge", "certification"])
        
        if category:
            tags.append(category)
        
        # Use forward slashes in filename for consistency
        filename = str(rel_path).replace("\\", "/")
        
        asset = {
            "id": base_name.lower().replace(" ", "-"),
            "name": display_name,
            "filename": filename,
            "type": asset_type,
            "tags": list(set(tags)),
            "url": f"/api/asset/{asset_type}s/{filename}",
        }
        
        if category:
            asset["category"] = category.title()
        
        assets.append(asset)
    
    return assets


@app.route("/")
def index():
    """Serve the main page."""
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    """Serve static files from frontend directory."""
    return send_from_directory(FRONTEND_DIR, path)


@app.route("/api/health")
def health_check():
    return jsonify({"status": "healthy", "version": "1.0.0-offline", "mode": "local"})


@app.route("/api/list-assets")
def list_assets():
    """List all available pre-loaded logos and badges from local folders."""
    asset_type = request.args.get("type", "all")
    response_data = {}
    
    if asset_type in ("all", "logos"):
        response_data["logos"] = list_local_assets(LOGOS_FOLDER, "logo")
    
    if asset_type in ("all", "badges"):
        response_data["badges"] = list_local_assets(BADGES_FOLDER, "badge")
    
    return jsonify(response_data)


@app.route("/api/asset/badges/<path:filename>")
def get_badge_asset(filename):
    """Serve a badge image from local folder."""
    file_path = BADGES_FOLDER / filename
    if not file_path.exists() or not file_path.is_file():
        abort(404)
    return send_file(file_path)


@app.route("/api/asset/logos/<path:filename>")
def get_logo_asset(filename):
    """Serve a logo image from local folder."""
    file_path = LOGOS_FOLDER / filename
    if not file_path.exists() or not file_path.is_file():
        abort(404)
    return send_file(file_path)


@app.route("/api/search")
def search():
    """Search assets by name or tags."""
    query = request.args.get("q", "").lower().strip()
    asset_type = request.args.get("type", "all")
    
    all_assets = []
    
    if asset_type in ("all", "logos"):
        all_assets.extend(list_local_assets(LOGOS_FOLDER, "logo"))
    
    if asset_type in ("all", "badges"):
        all_assets.extend(list_local_assets(BADGES_FOLDER, "badge"))
    
    if query:
        query_terms = query.split()
        results = []
        
        for asset in all_assets:
            name_lower = asset["name"].lower()
            tags = asset.get("tags", [])
            
            if query in name_lower:
                results.append(asset)
            elif any(query in tag for tag in tags):
                results.append(asset)
            elif all(any(term in name_lower or term in " ".join(tags) for term in query_terms) for term in query_terms):
                results.append(asset)
        
        return jsonify({"results": results, "total": len(results)})
    
    return jsonify({"results": all_assets, "total": len(all_assets)})


@app.route("/api/generate-gif", methods=["POST"])
def generate_gif():
    """Generate an animated GIF from uploaded and/or library images."""
    try:
        # Get settings from form data
        duration = int(request.form.get("duration", 1500))
        logo_duration = int(request.form.get("logoDuration", 2500))
        size = request.form.get("size", "320x180")
        background = request.form.get("background", "#FFFFFF")
        group_size = int(request.form.get("groupSize", 3))
        
        # Get ordered items
        ordered_badges = json.loads(request.form.get("orderedBadges", "[]"))
        ordered_logos = json.loads(request.form.get("orderedLogos", "[]"))
        
        # Get uploaded files
        uploaded_badges = request.files.getlist("badges")
        uploaded_logos = request.files.getlist("logos")
        
        # Collect badge images in order
        badge_images = []
        upload_badge_index = 0
        
        for item in ordered_badges:
            if item["type"] == "upload":
                if upload_badge_index < len(uploaded_badges):
                    file = uploaded_badges[upload_badge_index]
                    badge_images.append(file.read())
                    upload_badge_index += 1
            else:
                # Library item - load from local folder
                filename = item["filename"]
                file_path = BADGES_FOLDER / filename
                if file_path.exists():
                    badge_images.append(file_path.read_bytes())
        
        # Collect logo images in order
        logo_images = []
        upload_logo_index = 0
        
        for item in ordered_logos:
            if item["type"] == "upload":
                if upload_logo_index < len(uploaded_logos):
                    file = uploaded_logos[upload_logo_index]
                    logo_images.append(file.read())
                    upload_logo_index += 1
            else:
                # Library item - load from local folder
                filename = item["filename"]
                file_path = LOGOS_FOLDER / filename
                if file_path.exists():
                    logo_images.append(file_path.read_bytes())
        
        if not badge_images and not logo_images:
            return jsonify({"error": "No valid images provided"}), 400
        
        # Parse size
        width, height = 320, 180
        if "x" in size.lower():
            parts = size.lower().split("x")
            width = int(parts[0])
            height = int(parts[1])
        
        # Generate GIF
        config = GifConfig(
            size=(width, height),
            background=background,
            padding=5,
            group_size=group_size,
            duration=duration,
            logo_duration=logo_duration,
            loop=0,
        )
        
        gif_data = generate_gif_from_bytes(badge_images, logo_images, config)
        
        # Optionally save to output folder
        output_path = OUTPUT_DIR / "badge_slideshow.gif"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(gif_data)
        
        return send_file(
            BytesIO(gif_data),
            mimetype="image/gif",
            as_attachment=True,
            download_name="badge_slideshow.gif"
        )
    
    except Exception as e:
        print(f"Error generating GIF: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def open_browser():
    """Open the browser after a short delay."""
    import time
    time.sleep(1.5)
    webbrowser.open("http://localhost:5000")


def main():
    """Run the server."""
    print("=" * 50)
    print("Badge GIF Generator - Offline Mode")
    print("=" * 50)
    print(f"\nBadge folder: {BADGES_FOLDER}")
    print(f"Logo folder:  {LOGOS_FOLDER}")
    print(f"Output folder: {OUTPUT_DIR}")
    print(f"\nOpening http://localhost:5000 in your browser...")
    print("Press Ctrl+C to stop the server.\n")
    
    # Create folders if they don't exist
    BADGES_FOLDER.mkdir(parents=True, exist_ok=True)
    LOGOS_FOLDER.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Open browser in background thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Run the server
    app.run(host="localhost", port=5000, debug=False)


if __name__ == "__main__":
    main()
