# Badge GIF Generator - Azure VM Solution

A web-based solution for creating animated GIF slideshows from certification badges and logos. Deployed on an Azure Linux VM with HTTPS via Let's Encrypt, pulling code directly from GitHub.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Azure Linux VM (Ubuntu 22.04)                   │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  nginx (reverse proxy + static files + HTTPS)               │    │
│  │    ├── / → Static frontend (HTML/CSS/JS)                    │    │
│  │    └── /api/* → FastAPI backend (uvicorn :8000)             │    │
│  └─────────────────────────────────────────────────────────────┘    │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  FastAPI Backend                                             │    │
│  │    • /api/generate-gif - Create animated GIFs                │    │
│  │    • /api/categories - List badge categories                 │    │
│  │    • /api/badges/{category} - Get badges by category         │    │
│  │    • /api/logos - List available logos                       │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
              │ Private Endpoint                    │ GitHub
              ▼                                     ▼
┌─────────────────────────────────┐    ┌─────────────────────────────┐
│     Azure Blob Storage          │    │     GitHub Repository        │
│  ┌───────────┐  ┌───────────┐   │    │  • Application source code   │
│  │ ms-badges/│  │ ms-logos/ │   │    │  • Seed badge images         │
│  │ (by cat.) │  │           │   │    │  • Infrastructure (Bicep)    │
│  └───────────┘  └───────────┘   │    └─────────────────────────────┘
└─────────────────────────────────┘
```

## Project Structure

```
badge-gif-generator/
├── api/                          # FastAPI Backend (Python)
│   ├── main_vm.py                # FastAPI application entry point
│   ├── gif_generator.py          # Core GIF generation logic
│   ├── requirements.txt          # Python dependencies
│   └── tests/                    # Unit tests
├── frontend/                     # Static web frontend
│   ├── index.html                # Main application page
│   ├── css/
│   │   └── styles.css            # Application styles
│   └── js/
│       └── app.js                # Frontend JavaScript
├── assets/                       # Seed assets for blob storage
│   ├── badges/                   # Badge images (by category)
│   └── logos/                    # Logo images
├── infrastructure/               # Azure deployment (Bicep)
│   ├── main-vm.bicep             # VM infrastructure template
│   ├── vm-setup-github.sh        # VM provisioning script (pulls from GitHub)
│   └── parameters-vm.json        # Deployment parameters
├── deploy-vm.ps1                 # PowerShell deployment script
└── README.md                     # This file
```

## Local Development

### Prerequisites

- Python 3.11+
- Azure CLI (for deployment)

### Setup

1. **Create Python virtual environment:**
   ```powershell
   cd api
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. **Set environment variables:**
   ```powershell
   $env:STORAGE_ACCOUNT_NAME = "your-storage-account"  # Optional for local dev
   ```

3. **Run the FastAPI server:**
   ```powershell
   cd api
   uvicorn main_vm:app --reload --host 0.0.0.0 --port 8000
   ```

4. **Serve frontend (separate terminal):**
   ```powershell
   cd frontend
   python -m http.server 8080
   ```

5. **Open browser:** http://localhost:8080

### Offline Version

See the `Off Line/` folder for a standalone Flask-based version that runs entirely offline with local badge images.

## API Endpoints

### POST /api/generate-gif

Generate an animated GIF from uploaded images and selected assets.

**Request (multipart/form-data):**
- `badges[]` - Uploaded badge image files
- `selectedBadges` - JSON array of storage blob URLs for library badges
- `selectedLogos` - JSON array of storage blob URLs for logos
- `duration` - Frame duration in milliseconds (default: 1500)
- `logoDuration` - Logo frame duration in milliseconds (default: 2500)
- `size` - Canvas size as "WIDTHxHEIGHT" (default: "320x180")
- `background` - Background color hex or "transparent" (default: "#FFFFFF")
- `groupSize` - Badges per frame (default: 3)

**Response:**
- `200 OK` - Returns the generated GIF file (image/gif)
- `400 Bad Request` - Invalid parameters
- `500 Internal Server Error` - Generation failed

### GET /api/categories

List all badge categories (auto-detected from storage folder structure).

**Response:**
```json
["azure", "aws", "cisco", "comptia", "google", "itil", "microsoft"]
```

### GET /api/badges/{category}

Get all badges in a specific category.

**Response:**
```json
[
  {"name": "azure-fundamentals.png", "url": "https://..."},
  {"name": "azure-administrator.png", "url": "https://..."}
]
```

### GET /api/logos

List all available logos.

**Response:**
```json
[
  {"name": "microsoft.webp", "url": "https://..."},
  {"name": "azure.webp", "url": "https://..."}
]
```

### GET /api/health

Health check endpoint for monitoring.

**Response:**
```json
{"status": "healthy", "storage": "connected"}
```

## Deployment

### VM Deployment (Recommended)

The recommended deployment method uses an Azure VM that pulls code directly from GitHub:

```powershell
# Clone this repo (or fork it first)
git clone https://github.com/MicrosoftAzureAaron/badge-gif-generator.git
cd badge-gif-generator

# Deploy VM (will pull code from GitHub during provisioning)
.\deploy-vm.ps1 `
    -ResourceGroupName "rg-badge-gif-generator" `
    -Location "eastus2" `
    -GithubRepo "https://github.com/MicrosoftAzureAaron/badge-gif-generator.git" `
    -GithubBranch "main"
```

**GitHub Repository Requirements:**
- Repository must be **public** (or use a PAT for private repos)
- No secrets are stored in code - all sensitive values are passed at deploy time
- Badge images in `assets/badges/` will seed the storage account automatically

**To update deployed code:**
```bash
# SSH into VM
ssh azureuser@<vm-ip>

# Pull latest changes
cd /opt/badge-gif-repo && git pull

# Copy updated files
sudo cp -r api/* /opt/badge-gif-generator/api/
sudo cp -r frontend/* /opt/badge-gif-generator/frontend/

# Restart service
sudo systemctl restart badge-gif-generator
```

### Multi-Region Deployment

Deploy a secondary instance in another region sharing the same storage:

```powershell
# Get primary VNet ID
$primaryVNetId = az network vnet show `
    --resource-group rg-badge-gif-generator `
    --name vnet-badgegifgen `
    --query id -o tsv

# Deploy secondary
.\deploy-vm.ps1 `
    -ResourceGroupName "rg-badge-gif-generator-westus2" `
    -Location "westus2" `
    -ExistingStorageAccountName "stbadgegifgenXXXXX" `
    -ExistingStorageResourceGroup "rg-badge-gif-generator" `
    -PrimaryVNetId $primaryVNetId `
    -GithubRepo "https://github.com/MicrosoftAzureAaron/badge-gif-generator.git"
```

### VM Components

The deployed VM includes:

| Component | Description |
|-----------|-------------|
| **Ubuntu 22.04 LTS** | Base OS |
| **nginx** | Reverse proxy, static file serving, HTTPS termination |
| **uvicorn** | ASGI server running FastAPI on port 8000 |
| **certbot** | Let's Encrypt certificate automation |
| **systemd** | Service management (badge-gif-generator.service) |
| **Managed Identity** | Secure access to Azure Storage (no keys stored) |

### SSH Access

```powershell
# Connect to the VM
ssh -i "$env:USERPROFILE\.ssh\badge-vm-key" azureuser@badgegifgen.eastus2.cloudapp.azure.com

# Check service status
sudo systemctl status badge-gif-generator

# View logs
sudo journalctl -u badge-gif-generator -f
```

## Features

- **Drag & Drop Upload**: Easily upload your own badge images
- **Searchable Asset Library**: Find Microsoft logos and badges quickly
- **Live Preview**: See your badges before generating
- **Customizable Settings**: Adjust timing, size, background color
- **Instant Download**: Get your GIF immediately after generation
- **Responsive Design**: Works on desktop and mobile

## Configuration Options

| Setting | Default | Description |
|---------|---------|-------------|
| Duration | 1500ms | How long each badge frame displays |
| Logo Duration | 2500ms | How long logo frames display |
| Canvas Size | 320x180 | Output GIF dimensions |
| Background | #FFFFFF | Canvas background color |
| Group Size | 3 | Number of badges per frame |
| Loop | 0 (infinite) | Animation loop count |
