"""
Badge GIF Generator - FastAPI Web Server
Serves both the API and static frontend

This module provides:
- RESTful API endpoints for GIF generation
- Asset library listing and search
- Integration with Azure Blob Storage
- Static file serving for the web frontend

Version: 1.1.1
"""

import logging
import os
import sys
import json
from io import BytesIO
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, Response, JSONResponse

from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas
from azure.core.exceptions import AzureError

# Add shared module to path (for VM deployment structure)
APP_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(APP_DIR))

from shared.gif_generator import GifConfig, generate_gif_from_bytes, generate_gif_from_ordered_bytes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Badge GIF Generator",
    version="1.1.1",
    description="Generate animated GIFs from certification badges and logos"
)

# CORS Configuration
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

# Standard response models
class ErrorResponse:
    """Standard error response format."""
    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code


def get_blob_service_client() -> BlobServiceClient:
    """
    Get Azure Blob Service client using managed identity.
    
    Uses DefaultAzureCredential for secure, passwordless authentication.
    Requires STORAGE_ACCOUNT_NAME environment variable to be set.
    
    Returns:
        Initialized BlobServiceClient
        
    Raises:
        ValueError: If STORAGE_ACCOUNT_NAME environment variable is not set
        AzureError: If authentication fails
    """
    if not STORAGE_ACCOUNT_NAME:
        logger.error("STORAGE_ACCOUNT_NAME environment variable not set")
        raise ValueError("STORAGE_ACCOUNT_NAME environment variable is required")
    
    try:
        credential = DefaultAzureCredential()
        account_url = f"https://{STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
        logger.debug(f"Creating blob service client for {account_url}")
        return BlobServiceClient(account_url, credential=credential)
    except AzureError as exc:
        logger.error(f"Failed to authenticate with Azure: {exc}")
        raise
    except Exception as exc:
        logger.error(f"Unexpected error creating blob service client: {exc}")
        raise


def list_assets_from_container(container_name: str, asset_type: str) -> List[Dict[str, Any]]:
    """
    List all image assets from a blob container.
    
    Retrieves blob metadata and organizes by category if present in folder structure.
    Returns structured asset data with search tags.
    
    Args:
        container_name: Name of the blob container (e.g., 'ms-badges')
        asset_type: Type of asset for tagging ('logo' or 'badge')
        
    Returns:
        List of asset dictionaries with id, name, filename, type, tags, category, size
        
    Note:
        Returns empty list on error rather than raising, allowing graceful degradation
    """
    try:
        if not STORAGE_ACCOUNT_NAME:
            logger.warning("STORAGE_ACCOUNT_NAME not configured, cannot list assets")
            return []
        
        logger.info(f"Listing {asset_type}s from container {container_name}")
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(container_name)
        assets = []

        for blob in container_client.list_blobs():
            name = blob.name
            ext = os.path.splitext(name)[1].lower()

            if ext not in IMAGE_EXTENSIONS:
                logger.debug(f"Skipping {name}: unsupported extension {ext}")
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

            # Add type-specific tags
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
            logger.debug(f"Added asset: {display_name} ({blob.size} bytes)")

        logger.info(f"Listed {len(assets)} {asset_type}s from {container_name}")
        return assets
    except AzureError as exc:
        logger.error(f"Azure error listing assets from {container_name}: {exc}")
        return []
    except Exception as exc:
        logger.error(f"Error listing assets from {container_name}: {exc}")
        return []


def download_blob(container_name: str, blob_name: str) -> bytes:
    """
    Download a blob's content as bytes.
    
    Args:
        container_name: Name of the container
        blob_name: Name/path of the blob within the container
        
    Returns:
        Blob content as bytes
        
    Raises:
        AzureError: If blob download fails
        ValueError: If blob_name is empty or invalid
    """
    if not blob_name:
        raise ValueError("blob_name cannot be empty")
    
    try:
        logger.debug(f"Downloading blob {blob_name} from {container_name}")
        blob_service = get_blob_service_client()
        container_client = blob_service.get_container_client(container_name)
        blob_client = container_client.get_blob_client(blob_name)
        content = blob_client.download_blob().readall()
        logger.debug(f"Downloaded {len(content)} bytes for {blob_name}")
        return content
    except AzureError as exc:
        logger.error(f"Failed to download blob {blob_name}: {exc}")
        raise HTTPException(status_code=404, detail=f"Blob not found: {blob_name}") from exc
    except Exception as exc:
        logger.error(f"Unexpected error downloading blob: {exc}")
        raise


@app.get("/api/health")
def health_check() -> Dict[str, Any]:
    """
    Health check endpoint for container/load balancer probes.
    
    Returns:
        Dictionary with status and version information
    """
    logger.debug("Health check requested")
    return {
        "status": "healthy",
        "version": "1.1.1",
        "service": "Badge GIF Generator API"
    }


@app.get("/api/list-assets")
def list_assets(type: str = "all") -> Dict[str, List[Dict[str, Any]]]:
    """
    List all available pre-loaded logos and badges.
    
    Args:
        type: Asset type filter ('all', 'logos', or 'badges')
        
    Returns:
        Dictionary with 'logos' and/or 'badges' lists
    """
    logger.info(f"Listing assets with filter: {type}")
    response_data = {}

    if type in ("all", "logos"):
        response_data["logos"] = list_assets_from_container(LOGOS_CONTAINER, "logo")

    if type in ("all", "badges"):
        response_data["badges"] = list_assets_from_container(BADGES_CONTAINER, "badge")

    return response_data


@app.get("/api/search")
def search(q: str = "", type: str = "all") -> Dict[str, Any]:
    """
    Search assets by name or tags.
    
    Performs case-insensitive matching on asset names and tags.
    Results are ranked by relevance (exact name match scores higher).
    
    Args:
        q: Search query string (empty returns all assets)
        type: Asset type filter ('all', 'logos', or 'badges')
        
    Returns:
        Dictionary with 'results' list and 'total' count
    """
    logger.info(f"Search requested: q='{q}', type={type}")
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

            # Calculate relevance score
            score = 0
            for term in query_terms:
                if term in name_lower:
                    score += 2  # Name match is more relevant
                if any(term in tag for tag in tags):
                    score += 1  # Tag match is secondary

            if score > 0:
                results.append((score, asset))

        results.sort(key=lambda x: x[0], reverse=True)
        logger.info(f"Search returned {len(results)} results for '{q}'")
        return {"results": [asset for _, asset in results], "total": len(results)}

    logger.info(f"Search returned all {len(all_assets)} assets (no query)")
    return {"results": all_assets, "total": len(all_assets)}


@app.get("/api/asset/{container}/{filename:path}")
def get_asset(container: str, filename: str):
    """
    Proxy endpoint to serve blob assets.
    
    Args:
        container: Container name (ms-logos or ms-badges)
        filename: Asset filename/path within the container
        
    Returns:
        Image file with appropriate Content-Type
        
    Raises:
        HTTPException: 404 if container or asset not found
    """
    logger.debug(f"Asset requested: {container}/{filename}")
    if container not in [LOGOS_CONTAINER, BADGES_CONTAINER]:
        logger.warning(f"Invalid container requested: {container}")
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

        logger.info(f"Serving asset {filename} ({len(data)} bytes)")
        return Response(content=data, media_type=content_type)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error serving asset {filename}: {exc}")
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/api/generate-gif")
async def generate_gif_endpoint(
    duration: int = Form(1500),
    logoDuration: int = Form(2500),
    size: str = Form("320x180"),
    background: str = Form("#FFFFFF"),
    groupSize: int = Form(3),
    loop: int = Form(0),
    removeWhiteBg: bool = Form(False),
    badges: List[UploadFile] = File(default=[]),
    logos: List[UploadFile] = File(default=[]),
    selectedBadges: str = Form("[]"),
    selectedLogos: str = Form("[]"),
    orderedItems: str = Form("[]"),
    orderedBadges: str = Form("[]"),
    orderedLogos: str = Form("[]"),
) -> Response:
    """
    Generate an animated GIF from uploaded images and selected assets.
    
    Supports:
    - Uploaded files (multipart form upload)
    - Library assets from Azure Blob Storage
    - Custom ordering via JSON parameters
    - Configurable timing, size, colors, and grouping
    
    Args:
        duration: Duration per badge frame in milliseconds
        logoDuration: Duration per logo frame in milliseconds
        size: Canvas size as 'WIDTHxHEIGHT' (e.g., '320x180')
        background: Background color (hex, color name, or 'transparent')
        groupSize: Number of badges per frame
        loop: GIF loop count (0 = infinite)
        removeWhiteBg: If True, remove white backgrounds from images
        badges: Uploaded badge files
        logos: Uploaded logo files
        selectedBadges: JSON array of selected badge filenames from library
        selectedLogos: JSON array of selected logo filenames from library
        orderedItems: JSON array preserving combined drag/drop order
        orderedBadges: JSON array with ordering and source info for badges
        orderedLogos: JSON array with ordering and source info for logos
        
    Returns:
        GIF file as binary response with appropriate Content-Type
        
    Raises:
        HTTPException: 400 if no images provided or invalid parameters
        HTTPException: 500 if GIF generation fails
    """
    logger.info(f"GIF generation requested: size={size}, duration={duration}ms, " 
                f"groupSize={groupSize}, {len(badges)} badge uploads, {len(logos)} logo uploads")
    
    try:
        # Parse and validate size parameter
        try:
            width, height = size.lower().split("x")
            parsed_size = (int(width), int(height))
            logger.debug(f"Parsed size: {parsed_size}")
        except (ValueError, AttributeError) as exc:
            logger.warning(f"Invalid size format '{size}', using default")
            parsed_size = (320, 180)

        # Create GIF configuration
        config = GifConfig(
            size=parsed_size,
            background=background,
            padding=5,
            group_size=groupSize,
            duration=duration,
            logo_duration=logoDuration,
            loop=loop,
            remove_white_bg=removeWhiteBg
        )

        # Read all uploaded files
        logger.debug(f"Reading {len(badges)} badge uploads and {len(logos)} logo uploads")
        uploaded_badge_contents = []
        for idx, f in enumerate(badges):
            try:
                content = await f.read()
                if content:
                    uploaded_badge_contents.append(content)
                    logger.debug(f"Read badge upload {idx}: {len(content)} bytes")
            except Exception as exc:
                logger.error(f"Failed to read badge upload {idx}: {exc}")
                raise HTTPException(status_code=400, detail=f"Failed to read badge file: {f.filename}")

        uploaded_logo_contents = []
        for idx, f in enumerate(logos):
            try:
                content = await f.read()
                if content:
                    uploaded_logo_contents.append(content)
                    logger.debug(f"Read logo upload {idx}: {len(content)} bytes")
            except Exception as exc:
                logger.error(f"Failed to read logo upload {idx}: {exc}")
                raise HTTPException(status_code=400, detail=f"Failed to read logo file: {f.filename}")

        # Parse ordering information
        try:
            ordered_items_list = json.loads(orderedItems) if orderedItems else []
            ordered_badges_list = json.loads(orderedBadges) if orderedBadges else []
            ordered_logos_list = json.loads(orderedLogos) if orderedLogos else []
        except json.JSONDecodeError as exc:
            logger.warning(f"Invalid JSON in ordering parameters: {exc}")
            ordered_items_list = []
            ordered_badges_list = []
            ordered_logos_list = []

        badge_data: List[bytes] = []
        logo_data: List[bytes] = []

        # Preferred path: preserve combined drag/drop order from frontend.
        if ordered_items_list:
            logger.debug(f"Processing {len(ordered_items_list)} ordered items")
            ordered_media: List[tuple[str, bytes]] = []

            for item in ordered_items_list:
                kind = item.get("kind")
                source_type = item.get("type")

                if kind not in ("badge", "logo"):
                    continue

                if source_type == "upload":
                    try:
                        upload_index = int(item.get("index", -1))
                    except (TypeError, ValueError):
                        upload_index = -1

                    uploaded_list = uploaded_badge_contents if kind == "badge" else uploaded_logo_contents
                    if 0 <= upload_index < len(uploaded_list):
                        ordered_media.append((kind, uploaded_list[upload_index]))
                elif source_type == "library" and item.get("filename"):
                    filename = item["filename"]
                    container = BADGES_CONTAINER if kind == "badge" else LOGOS_CONTAINER
                    try:
                        data = download_blob(container, filename)
                        ordered_media.append((kind, data))
                    except Exception as exc:
                        logger.warning(f"Could not download {kind} {filename}: {exc}")

            if ordered_media:
                badge_data = [data for kind, data in ordered_media if kind == "badge"]
                logo_data = [data for kind, data in ordered_media if kind == "logo"]
                logger.info(
                    f"Generating ordered GIF with {len(ordered_media)} items "
                    f"({len(badge_data)} badges, {len(logo_data)} logos)"
                )
                gif_bytes = generate_gif_from_ordered_bytes(ordered_media, config)
                logger.info(f"GIF generated successfully: {len(gif_bytes)} bytes")
                return Response(
                    content=gif_bytes,
                    media_type="image/gif",
                    headers={"Content-Disposition": "attachment; filename=badge_slideshow.gif"}
                )

        # Process badges with ordering if provided
        if ordered_badges_list:
            logger.debug(f"Processing {len(ordered_badges_list)} ordered badge items")
            for item in ordered_badges_list:
                if item.get('type') == 'upload':
                    try:
                        upload_idx = int(item.get('index', -1))
                    except (TypeError, ValueError):
                        upload_idx = -1
                    if 0 <= upload_idx < len(uploaded_badge_contents):
                        badge_data.append(uploaded_badge_contents[upload_idx])
                elif item.get('type') == 'library' and item.get('filename'):
                    try:
                        data = download_blob(BADGES_CONTAINER, item['filename'])
                        badge_data.append(data)
                        logger.debug(f"Downloaded badge: {item['filename']}")
                    except Exception as exc:
                        logger.warning(f"Could not download badge {item['filename']}: {exc}")
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
                    logger.debug(f"Downloaded badge: {filename}")
                except Exception as exc:
                    logger.warning(f"Could not download badge {filename}: {exc}")

        # Process logos with ordering if provided
        if ordered_logos_list:
            logger.debug(f"Processing {len(ordered_logos_list)} ordered logo items")
            for item in ordered_logos_list:
                if item.get('type') == 'upload':
                    try:
                        upload_idx = int(item.get('index', -1))
                    except (TypeError, ValueError):
                        upload_idx = -1
                    if 0 <= upload_idx < len(uploaded_logo_contents):
                        logo_data.append(uploaded_logo_contents[upload_idx])
                elif item.get('type') == 'library' and item.get('filename'):
                    try:
                        data = download_blob(LOGOS_CONTAINER, item['filename'])
                        logo_data.append(data)
                        logger.debug(f"Downloaded logo: {item['filename']}")
                    except Exception as exc:
                        logger.warning(f"Could not download logo {item['filename']}: {exc}")
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
                    logger.debug(f"Downloaded logo: {filename}")
                except Exception as exc:
                    logger.warning(f"Could not download logo {filename}: {exc}")

        if not badge_data and not logo_data:
            logger.warning("GIF generation requested with no images")
            return JSONResponse(
                status_code=400,
                content={"error": "No images provided. Upload badges/logos or select from the library."}
            )

        logger.info(f"Generating GIF with {len(badge_data)} badges and {len(logo_data)} logos")
        
        # Generate the GIF
        gif_bytes = generate_gif_from_bytes(badge_data, logo_data, config)

        logger.info(f"GIF generated successfully: {len(gif_bytes)} bytes")
        return Response(
            content=gif_bytes,
            media_type="image/gif",
            headers={"Content-Disposition": "attachment; filename=badge_slideshow.gif"}
        )

    except HTTPException:
        raise
    except ValueError as exc:
        logger.error(f"Validation error during GIF generation: {exc}")
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.error(f"Unexpected error generating GIF: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to generate GIF: {str(exc)}", "type": type(exc).__name__}
        )


# Serve static frontend files
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if FRONTEND_DIR.exists():
    logger.info(f"Mounting static files from {FRONTEND_DIR}")
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    logger.warning(f"Frontend directory not found at {FRONTEND_DIR}")


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting Badge GIF Generator API server")
    logger.info(f"Storage Account: {STORAGE_ACCOUNT_NAME or 'Not configured'}")
    logger.info(f"Frontend Directory: {FRONTEND_DIR}")
    
    # Run with detailed logging
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
