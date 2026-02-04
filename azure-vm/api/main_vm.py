"""
Badge GIF Generator - FastAPI Web Server
Serves both the API and static frontend
"""

import os
import sys
import json
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient

# Add shared module to path (for VM deployment structure)
APP_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(APP_DIR))

from shared.gif_generator import GifConfig, generate_gif_from_bytes

app = FastAPI(title="Badge GIF Generator")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
STORAGE_ACCOUNT_NAME = os.environ.get("STORAGE_ACCOUNT_NAME", "")
LOGOS_CONTAINER = "ms-logos"
BADGES_CONTAINER = "ms-badges"

IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"})


def get_blob_service_client():
    """Get blob service client using managed identity."""
    credential = DefaultAzureCredential()
    account_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
    return BlobServiceClient(account_url, credential=credential)


def list_assets_from_container(container_name: str, asset_type: str) -> List[dict]:
    """List all image assets from a blob container."""
    try:
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(container_name)
        assets = []

        for blob in container_client.list_blobs():
            name = blob.name
            ext = os.path.splitext(name)[1].lower()

            if ext not in IMAGE_EXTENSIONS:
                continue

            # Check if blob is in a subfolder (category/filename.ext)
            parts = name.split("/")
            if len(parts) > 1:
                category = parts[0].lower()
                filename_only = parts[-1]
            else:
                category = None
                filename_only = name
            
            base_name = os.path.splitext(os.path.basename(filename_only))[0]
            display_name = base_name.replace("-", " ").replace("_", " ").title()
            tags = [t.lower() for t in base_name.replace("-", " ").replace("_", " ").split()]

            if asset_type == "logo":
                tags.append("logo")
            elif asset_type == "badge":
                tags.extend(["badge", "certification"])
            
            # Add category to tags if present
            if category:
                tags.append(category)

            asset = {
                "id": base_name.lower().replace(" ", "-"),
                "name": display_name,
                "filename": name,
                "type": asset_type,
                "tags": list(set(tags)),
                "size": blob.size
            }
            
            if category:
                asset["category"] = category.title()
            
            assets.append(asset)

        return assets
    except Exception as e:
        print(f"Error listing assets from {container_name}: {e}")
        return []


def download_blob(container_name: str, blob_name: str) -> bytes:
    """Download a blob's content as bytes."""
    blob_service = get_blob_service_client()
    container_client = blob_service.get_container_client(container_name)
    blob_client = container_client.get_blob_client(blob_name)
    return blob_client.download_blob().readall()


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/api/list-assets")
def list_assets(type: str = "all"):
    """List all available pre-loaded logos and badges."""
    response_data = {}

    if type in ("all", "logos"):
        response_data["logos"] = list_assets_from_container(LOGOS_CONTAINER, "logo")

    if type in ("all", "badges"):
        response_data["badges"] = list_assets_from_container(BADGES_CONTAINER, "badge")

    return response_data


@app.get("/api/search")
def search(q: str = "", type: str = "all"):
    """Search assets by name or tags."""
    all_assets = []

    if type in ("all", "logos"):
        all_assets.extend(list_assets_from_container(LOGOS_CONTAINER, "logo"))

    if type in ("all", "badges"):
        all_assets.extend(list_assets_from_container(BADGES_CONTAINER, "badge"))

    if q:
        query_lower = q.lower().strip()
        query_terms = query_lower.split()
        results = []

        for asset in all_assets:
            name_lower = asset["name"].lower()
            tags = asset.get("tags", [])

            score = 0
            for term in query_terms:
                if term in name_lower:
                    score += 2
                if any(term in tag for tag in tags):
                    score += 1

            if score > 0:
                results.append((score, asset))

        results.sort(key=lambda x: x[0], reverse=True)
        return {"results": [asset for _, asset in results], "total": len(results)}

    return {"results": all_assets, "total": len(all_assets)}


@app.get("/api/asset/{container}/{filename:path}")
def get_asset(container: str, filename: str):
    """Proxy endpoint to serve blob assets."""
    if container not in [LOGOS_CONTAINER, BADGES_CONTAINER]:
        raise HTTPException(status_code=404, detail="Container not found")

    try:
        data = download_blob(container, filename)
        ext = os.path.splitext(filename)[1].lower()
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".webp": "image/webp",
        }.get(ext, "application/octet-stream")

        return Response(content=data, media_type=content_type)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/generate-gif")
async def generate_gif_endpoint(
    duration: int = Form(1500),
    logoDuration: int = Form(2500),
    size: str = Form("320x180"),
    background: str = Form("#FFFFFF"),
    groupSize: int = Form(3),
    loop: int = Form(0),
    badges: List[UploadFile] = File(default=[]),
    logos: List[UploadFile] = File(default=[]),
    selectedBadges: str = Form("[]"),
    selectedLogos: str = Form("[]"),
    orderedBadges: str = Form("[]"),
    orderedLogos: str = Form("[]"),
):
    """Generate an animated GIF from uploaded images and selected assets."""
    try:
        # Parse size
        try:
            width, height = size.lower().split("x")
            parsed_size = (int(width), int(height))
        except Exception:
            parsed_size = (320, 180)

        config = GifConfig(
            size=parsed_size,
            background=background,
            padding=5,
            group_size=groupSize,
            duration=duration,
            logo_duration=logoDuration,
            loop=loop
        )

        # Read all uploaded files first (before we process ordering)
        uploaded_badge_contents = []
        for f in badges:
            content = await f.read()
            if content:
                uploaded_badge_contents.append(content)

        uploaded_logo_contents = []
        for f in logos:
            content = await f.read()
            if content:
                uploaded_logo_contents.append(content)

        # Parse ordering information
        try:
            ordered_badges_list = json.loads(orderedBadges) if orderedBadges else []
            ordered_logos_list = json.loads(orderedLogos) if orderedLogos else []
        except json.JSONDecodeError:
            ordered_badges_list = []
            ordered_logos_list = []

        badge_data: List[bytes] = []
        logo_data: List[bytes] = []

        # If we have ordering info, use it
        if ordered_badges_list:
            upload_idx = 0
            for item in ordered_badges_list:
                if item.get('type') == 'upload':
                    if upload_idx < len(uploaded_badge_contents):
                        badge_data.append(uploaded_badge_contents[upload_idx])
                        upload_idx += 1
                elif item.get('type') == 'library' and item.get('filename'):
                    try:
                        data = download_blob(BADGES_CONTAINER, item['filename'])
                        badge_data.append(data)
                    except Exception as e:
                        print(f"Could not download badge {item['filename']}: {e}")
        else:
            # Fallback: use old behavior
            badge_data = uploaded_badge_contents[:]
            try:
                selected_badges = json.loads(selectedBadges) if selectedBadges else []
            except json.JSONDecodeError:
                selected_badges = []
            for filename in selected_badges:
                try:
                    data = download_blob(BADGES_CONTAINER, filename)
                    badge_data.append(data)
                except Exception as e:
                    print(f"Could not download badge {filename}: {e}")

        if ordered_logos_list:
            upload_idx = 0
            for item in ordered_logos_list:
                if item.get('type') == 'upload':
                    if upload_idx < len(uploaded_logo_contents):
                        logo_data.append(uploaded_logo_contents[upload_idx])
                        upload_idx += 1
                elif item.get('type') == 'library' and item.get('filename'):
                    try:
                        data = download_blob(LOGOS_CONTAINER, item['filename'])
                        logo_data.append(data)
                    except Exception as e:
                        print(f"Could not download logo {item['filename']}: {e}")
        else:
            # Fallback: use old behavior
            logo_data = uploaded_logo_contents[:]
            try:
                selected_logos = json.loads(selectedLogos) if selectedLogos else []
            except json.JSONDecodeError:
                selected_logos = []
            for filename in selected_logos:
                try:
                    data = download_blob(LOGOS_CONTAINER, filename)
                    logo_data.append(data)
                except Exception as e:
                    print(f"Could not download logo {filename}: {e}")

        if not badge_data and not logo_data:
            return JSONResponse(
                status_code=400,
                content={"error": "No images provided. Upload badges/logos or select from the library."}
            )

        # Generate the GIF
        gif_bytes = generate_gif_from_bytes(badge_data, logo_data, config)

        return Response(
            content=gif_bytes,
            media_type="image/gif",
            headers={"Content-Disposition": "attachment; filename=badge_slideshow.gif"}
        )

    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        print(f"Error generating GIF: {e}")
        return JSONResponse(status_code=500, content={"error": f"Failed to generate GIF: {str(e)}"})


# Serve static frontend
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
