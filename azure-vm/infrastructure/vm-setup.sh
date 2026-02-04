#!/bin/bash
# VM Setup Script for Badge GIF Generator
# This script is run by the Custom Script Extension during VM deployment
# Environment variables set by Bicep deployment:
#   CERT_EMAIL - Email for Let's Encrypt certificate
#   CERT_DOMAIN - DNS domain name for the VM
#   STORAGE_ACCOUNT_NAME - Azure Storage account name

set -e

# Log file
LOG_FILE="/var/log/badge-gif-setup.log"
exec > >(tee -a $LOG_FILE) 2>&1

echo "=========================================="
echo "Badge GIF Generator VM Setup"
echo "Started: $(date)"
echo "CERT_DOMAIN: ${CERT_DOMAIN:-not set}"
echo "CERT_EMAIL: ${CERT_EMAIL:-not set}"
echo "STORAGE_ACCOUNT_NAME: ${STORAGE_ACCOUNT_NAME:-not set}"
echo "=========================================="

# Update system
echo "Updating system packages..."
apt-get update
apt-get upgrade -y

# Install dependencies
echo "Installing dependencies..."
apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    nginx \
    git \
    curl \
    unzip \
    certbot \
    python3-certbot-nginx

# Install Azure CLI
echo "Installing Azure CLI..."
curl -sL https://aka.ms/InstallAzureCLIDeb | bash

# Create app directory
APP_DIR="/opt/badge-gif-generator"
echo "Creating application directory: $APP_DIR"
mkdir -p $APP_DIR
mkdir -p $APP_DIR/api
mkdir -p $APP_DIR/frontend

# Create Python virtual environment
echo "Creating Python virtual environment..."
python3.11 -m venv $APP_DIR/venv

# Create requirements.txt
cat > $APP_DIR/api/requirements.txt << 'EOF'
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
python-multipart>=0.0.6
Pillow>=10.0.0
azure-storage-blob>=12.0.0
azure-identity>=1.15.0
aiofiles>=23.2.0
EOF

# Install Python packages
echo "Installing Python packages..."
$APP_DIR/venv/bin/pip install --upgrade pip
$APP_DIR/venv/bin/pip install -r $APP_DIR/api/requirements.txt

# Create placeholder for app files (will be deployed separately)
echo "Creating placeholder files..."

cat > $APP_DIR/api/main.py << 'PYTHON_EOF'
"""
Badge GIF Generator - FastAPI Web Server
Serves both the API and static frontend
"""

import os
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

from gif_generator import GifConfig, generate_gif_from_bytes

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
            
            base_name = os.path.splitext(os.path.basename(name))[0]
            display_name = base_name.replace("-", " ").replace("_", " ").title()
            tags = [t.lower() for t in base_name.replace("-", " ").replace("_", " ").split()]
            
            if asset_type == "logo":
                tags.append("logo")
            elif asset_type == "badge":
                tags.extend(["badge", "certification"])
            
            assets.append({
                "id": base_name.lower().replace(" ", "-"),
                "name": display_name,
                "filename": name,
                "type": asset_type,
                "tags": list(set(tags)),
                "size": blob.size
            })
        
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
        
        badge_data: List[bytes] = []
        logo_data: List[bytes] = []
        
        # Process uploaded badges
        for f in badges:
            content = await f.read()
            if content:
                badge_data.append(content)
        
        # Process uploaded logos
        for f in logos:
            content = await f.read()
            if content:
                logo_data.append(content)
        
        # Get selected pre-loaded assets
        try:
            selected_badges = json.loads(selectedBadges) if selectedBadges else []
            selected_logos = json.loads(selectedLogos) if selectedLogos else []
        except json.JSONDecodeError:
            selected_badges = []
            selected_logos = []
        
        # Download selected pre-loaded badges
        for filename in selected_badges:
            try:
                data = download_blob(BADGES_CONTAINER, filename)
                badge_data.append(data)
            except Exception as e:
                print(f"Could not download badge {filename}: {e}")
        
        # Download selected pre-loaded logos
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
PYTHON_EOF

# Create gif_generator.py (copy from api folder logic)
cat > $APP_DIR/api/gif_generator.py << 'PYTHON_EOF'
"""
Core GIF generation logic
"""

from dataclasses import dataclass
from io import BytesIO
from typing import List, Sequence, Tuple

from PIL import Image, ImageColor, ImageOps


@dataclass(frozen=True)
class GifConfig:
    size: Tuple[int, int] = (320, 180)
    background: str = "#FFFFFF"
    padding: int = 5
    group_size: int = 3
    duration: int = 1500
    logo_duration: int = 2500
    loop: int = 0


def parse_color(color_text: str) -> Tuple[int, int, int, int]:
    try:
        color = ImageColor.getrgb(color_text)
        if len(color) == 3:
            return (*color, 255)
        return color
    except Exception as exc:
        raise ValueError(f"Invalid color: {color_text}") from exc


def compose_badge_frame(
    image: Image.Image,
    size: Tuple[int, int],
    background_color: Tuple[int, int, int, int],
    padding: int,
) -> Image.Image:
    canvas = Image.new("RGBA", size, color=background_color)
    safe_width = max(1, size[0] - padding * 2)
    safe_height = max(1, size[1] - padding * 2)
    badge = ImageOps.contain(image, (safe_width, safe_height), Image.Resampling.LANCZOS)
    offset = ((size[0] - badge.width) // 2, (size[1] - badge.height) // 2)
    canvas.paste(badge, offset, badge if badge.mode == "RGBA" else None)
    return canvas


def compose_multi_badge_frame(
    images: Sequence[Image.Image],
    size: Tuple[int, int],
    background_color: Tuple[int, int, int, int],
    padding: int,
) -> Image.Image:
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
        badge = ImageOps.contain(image, (column_width, safe_height), Image.Resampling.LANCZOS)
        column_x = start_x + index * (column_width + spacing)
        x = column_x + (column_width - badge.width) // 2
        y = padding + (safe_height - badge.height) // 2
        canvas.paste(badge, (x, y), badge if badge.mode == "RGBA" else None)
    return canvas


def group_images(images: Sequence[Image.Image], group_size: int) -> List[List[Image.Image]]:
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


def load_image_from_bytes(image_data: bytes) -> Image.Image:
    image = Image.open(BytesIO(image_data))
    return image.convert("RGBA")


def generate_gif(
    badge_images: List[Image.Image],
    logo_images: List[Image.Image],
    config: GifConfig,
) -> bytes:
    background_color = parse_color(config.background)
    frames: List[Image.Image] = []
    durations: List[int] = []

    if badge_images:
        grouped_badges = group_images(badge_images, config.group_size)
        for group in grouped_badges:
            frame = compose_multi_badge_frame(group, config.size, background_color, config.padding)
            frames.append(frame)
            durations.append(config.duration)

    for logo in logo_images:
        frame = compose_badge_frame(logo, config.size, background_color, config.padding)
        frames.append(frame)
        durations.append(config.logo_duration)

    if not frames:
        raise ValueError("No images provided to generate GIF.")

    output = BytesIO()
    first_frame = frames[0]
    additional_frames = frames[1:] if len(frames) > 1 else []
    
    first_frame.save(
        output,
        format="GIF",
        save_all=True,
        append_images=additional_frames,
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
    badge_images = [load_image_from_bytes(data) for data in badge_data]
    logo_images = [load_image_from_bytes(data) for data in logo_data]
    return generate_gif(badge_images, logo_images, config)
PYTHON_EOF

# Create systemd service
echo "Creating systemd service..."
cat > /etc/systemd/system/badge-gif-generator.service << EOF
[Unit]
Description=Badge GIF Generator Web Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR/api
Environment="STORAGE_ACCOUNT_NAME="
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Get the VM's public DNS name from Azure metadata
echo "Getting VM DNS name..."
VM_DNS_NAME=$(curl -s -H Metadata:true "http://169.254.169.254/metadata/instance/network/interface/0/ipv4/ipAddress/0/publicIpAddress?api-version=2021-02-01&format=text" 2>/dev/null || echo "")

# Use CERT_DOMAIN from environment if set, otherwise try to get from metadata
if [ -n "$CERT_DOMAIN" ]; then
    SERVER_NAME="$CERT_DOMAIN"
    echo "Using domain from deployment: $SERVER_NAME"
elif [ -n "$VM_DNS_NAME" ]; then
    SERVER_NAME="$VM_DNS_NAME"
    echo "Using domain from metadata: $SERVER_NAME"
else
    SERVER_NAME="_"
    echo "Could not determine DNS name, using wildcard"
fi

# Configure Nginx as reverse proxy
echo "Configuring Nginx..."
cat > /etc/nginx/sites-available/badge-gif-generator << EOF
server {
    listen 80;
    server_name ${SERVER_NAME} _;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
    }
}
EOF

# Enable site
ln -sf /etc/nginx/sites-available/badge-gif-generator /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test and reload Nginx
nginx -t
systemctl reload nginx

# Enable and start the service (will fail until storage account is configured)
systemctl daemon-reload
systemctl enable badge-gif-generator

# Attempt to set up Let's Encrypt certificate automatically
# This will only work if the DNS name resolves to this VM and email is provided
echo ""
echo "Attempting to configure Let's Encrypt certificate..."

# Use environment variables passed from Bicep (with fallbacks)
CERT_DOMAIN="${CERT_DOMAIN:-$SERVER_NAME}"
CERT_EMAIL="${CERT_EMAIL:-}"

if [ -z "$CERT_EMAIL" ]; then
    echo "No CERT_EMAIL provided, skipping automatic HTTPS setup."
    echo "Run manually: sudo certbot --nginx -d $CERT_DOMAIN --email your-email@example.com"
elif [ "$CERT_DOMAIN" = "_" ]; then
    echo "No domain name configured, skipping HTTPS setup."
else
    # Wait a bit for DNS to propagate
    sleep 10

    # Try to get certificate (non-interactive, will fail gracefully if DNS not ready)
    if certbot --nginx -d "$CERT_DOMAIN" --non-interactive --agree-tos --email "$CERT_EMAIL" --redirect 2>/dev/null; then
        echo "HTTPS certificate installed successfully!"
    else
        echo "Could not auto-configure HTTPS certificate."
        echo "Run manually after deployment: sudo certbot --nginx -d $CERT_DOMAIN --email $CERT_EMAIL"
    fi
fi

echo "=========================================="
echo "VM Setup Complete!"
echo "Finished: $(date)"
echo "=========================================="
echo ""
echo "Application directory: $APP_DIR"
echo "Domain: $CERT_DOMAIN"
echo ""
echo "Next steps (if not already done):"
echo "1. Run: sudo systemctl start badge-gif-generator"
echo ""
echo "If HTTPS was not configured automatically, run:"
echo "  sudo certbot --nginx -d $CERT_DOMAIN --email your-email@example.com"
